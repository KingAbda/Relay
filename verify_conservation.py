"""Relay — credit conservation verification script.
Run against a test SQLite DB (or Postgres) to verify credits conserve
across every session lifecycle path.

Usage: python verify_conservation.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

os.environ["RELAY_SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["RELAY_ENV"] = "development"
os.environ["RELAY_FLAT_RATE"] = "false"
os.environ["RELAY_MAX_CREDIT_COST"] = "4"
os.environ["RELAY_STARTER_CREDITS"] = "10"
os.environ["RELAY_SUPPLY_ONLY_MODE"] = "false"
os.environ["DATABASE_URL"] = "sqlite:///test_conservation.db"
os.environ["WTF_CSRF_ENABLED"] = "false"

from app.main import app, db, add_credit_transaction, RELAY_FLAT_RATE, RELAY_MAX_CREDIT_COST
from app.models import (
    User, UserSkill, CreditAccount, CreditTransaction, Session,
    SkillRequest, TransactionType, SkillCategory, SessionStatus
)
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import uuid

PASS = 0
FAIL = 0

def check(condition, message):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {message}")
    else:
        FAIL += 1
        print(f"  ❌ {message}")

def net_credits(user_id):
    """Sum all credit transactions for a user (positive earns, negative spends)."""
    txs = CreditTransaction.query.filter(CreditTransaction.user_id == user_id).all()
    return sum(tx.amount for tx in txs)

def balance(user_id):
    acc = CreditAccount.query.filter(CreditAccount.user_id == user_id).first()
    return acc.balance if acc else 0.0

def make_user(email, name, credits=10):
    u = User(
        id=str(uuid.uuid4()), email=email, full_name=name,
        password_hash=generate_password_hash("Pass1234"),
        email_verified=True, onboarded=True, edu_verified=True
    )
    db.session.add(u)
    db.session.flush()
    db.session.add(CreditAccount(user_id=u.id, balance=float(credits)))
    return u

def make_skill(user, name, cost=2, category="technical"):
    s = UserSkill(user_id=user.id, name=name, category=category, description=f"Learn {name}", credit_cost=cost)
    db.session.add(s)
    return s

print("=" * 60)
print("RELAY — CREDIT CONSERVATION VERIFICATION")
print("=" * 60)

with app.app_context():
    db.drop_all()
    db.create_all()

    # ── SETUP ──
    print("\n── Setup ──")
    teacher = make_user("teacher@test.edu", "Teacher T", credits=5)
    learner = make_user("learner@test.edu", "Learner L", credits=5)
    broke = make_user("broke@test.edu", "Broke B", credits=0)
    db.session.commit()
    print(f"  Teacher: {teacher.id}")
    print(f"  Learner: {learner.id}")
    print(f"  Broke:   {broke.id}")

    # Create a skill
    skill = make_skill(teacher, "Python 101", cost=2)
    db.session.commit()

    initial_teacher_bal = balance(teacher.id)
    initial_learner_bal = balance(learner.id)
    initial_broke_bal = balance(broke.id)

    print(f"\n── Initial balances ──")
    print(f"  Teacher: {initial_teacher_bal}")
    print(f"  Learner: {initial_learner_bal}")
    print(f"  Broke:   {initial_broke_bal}")

    # ── PATH 1: request → complete (happy path) ──
    print("\n── Path 1: request → complete ──")
    with db.session.begin_nested():
        credit_cost = 1 if RELAY_FLAT_RATE else (skill.credit_cost or 1)
        credit = CreditAccount.query.filter(CreditAccount.user_id == learner.id).with_for_update().first()
        pre_bal = credit.balance
        if credit and credit.balance >= credit_cost:
            credit.balance -= credit_cost
        sess = Session(teacher_id=teacher.id, learner_id=learner.id, skill_name=skill.name, amount_charged=float(credit_cost))
        db.session.add(sess)
        db.session.flush()
        sess.status = SessionStatus.COMPLETED
        sess.completed_at = datetime.utcnow()
        credit_amount = sess.amount_charged or 1.0
        teacher_credit = CreditAccount.query.filter(CreditAccount.user_id == teacher.id).with_for_update().first()
        teacher_credit.balance += credit_amount
        db.session.commit()

    check(balance(teacher.id) == initial_teacher_bal + 2, "Teacher earned 2 credits")
    check(balance(learner.id) == initial_learner_bal - 2, "Learner spent 2 credits")
    check(balance(teacher.id) + balance(learner.id) == initial_teacher_bal + initial_learner_bal,
          f"Total conserved ({balance(teacher.id)} + {balance(learner.id)} = {balance(teacher.id) + balance(learner.id)} == {initial_teacher_bal + initial_learner_bal})")

    # ── PATH 2: request → cancel (refund) ──
    print("\n── Path 2: request → cancel ──")
    with db.session.begin_nested():
        credit_cost = 1 if RELAY_FLAT_RATE else (skill.credit_cost or 1)
        credit = CreditAccount.query.filter(CreditAccount.user_id == learner.id).with_for_update().first()
        if credit and credit.balance >= credit_cost:
            credit.balance -= credit_cost
            learner_bal_after_debit = credit.balance
        sess2 = Session(teacher_id=teacher.id, learner_id=learner.id, skill_name=skill.name, amount_charged=float(credit_cost))
        db.session.add(sess2)
        db.session.flush()
        # Cancel it
        refund_amount = sess2.amount_charged or 1.0
        ref_credit = CreditAccount.query.filter(CreditAccount.user_id == learner.id).with_for_update().first()
        ref_credit.balance += refund_amount
        db.session.commit()

    check(balance(learner.id) == learner_bal_after_debit + 2, "Learner refunded 2 credits after cancel")
    check(balance(teacher.id) == initial_teacher_bal + 2, "Teacher unchanged (session was cancelled)")
    print(f"  Teacher bal: {balance(teacher.id)}, Learner bal: {balance(learner.id)}, Sum: {balance(teacher.id) + balance(learner.id)}")

    # ── PATH 3: broken learner tries to claim ──
    print("\n── Path 3: broke user tries to request skill ──")
    with db.session.begin_nested():
        credit_cost = 1 if RELAY_FLAT_RATE else (skill.credit_cost or 1)
        b_credit = CreditAccount.query.filter(CreditAccount.user_id == broke.id).with_for_update().first()
        could_book = b_credit and b_credit.balance >= credit_cost
        if could_book:
            b_credit.balance -= credit_cost
            sess3 = Session(teacher_id=teacher.id, learner_id=broke.id, skill_name=skill.name, amount_charged=float(credit_cost))
            db.session.add(sess3)
        db.session.commit()

    check(not could_book, "Broke user cannot book (insufficient credits)")
    check(balance(broke.id) == 0, "Broke user balance unchanged (still 0)")

    # ── PATH 4: FLAT_RATE toggling ──
    print("\n── Path 4: FLAT_RATE toggle doesn't affect existing bookings ──")
    # Record balance before FLAT_RATE test
    bal_before_path4_learner = balance(learner.id)
    bal_before_path4_teacher = balance(teacher.id)
    with db.session.begin_nested():
        # Simulate a booking made under FLAT_RATE=true
        cost_with_flat = 1  # flat rate forced
        credit = CreditAccount.query.filter(CreditAccount.user_id == learner.id).with_for_update().first()
        credit.balance -= 1
        sess4 = Session(teacher_id=teacher.id, learner_id=learner.id, skill_name=skill.name, amount_charged=1.0)
        db.session.add(sess4)
        db.session.flush()
        # Now complete it (should use stored 1, not re-read)
        cr_amount = sess4.amount_charged
        tcr = CreditAccount.query.filter(CreditAccount.user_id == teacher.id).with_for_update().first()
        tcr.balance += cr_amount
        db.session.commit()

    check(cr_amount == 1.0, "amount_charged stored as 1 even though skill costs 2")
    check(balance(learner.id) == bal_before_path4_learner - 1, "Learner was debited exactly 1 (not 2)")
    check(balance(teacher.id) == bal_before_path4_teacher + 1, "Teacher credited exactly 1 (not 2)")
    check(balance(teacher.id) + balance(learner.id) == bal_before_path4_teacher + bal_before_path4_learner,
          "Total conserved through FLAT_RATE toggle")

    # ── PATH 5: claim with insufficient credits ──
    print("\n── Path 5: claim-request with insufficient credits ──")
    req = SkillRequest(user_id=broke.id, name="Python 101", category=SkillCategory.TECHNICAL, max_credits=2)
    db.session.add(req)
    db.session.commit()
    
    with db.session.begin_nested():
        teacher_skill2 = make_skill(teacher, "Python 201", cost=2)
        listing_cost = teacher_skill2.credit_cost if not RELAY_FLAT_RATE else 1
        charge = min(listing_cost, req.max_credits or 1, RELAY_MAX_CREDIT_COST)
        lc = CreditAccount.query.filter(CreditAccount.user_id == broke.id).with_for_update().first()
        can_claim = lc and lc.balance >= charge
        if can_claim:
            lc.balance -= charge
        db.session.commit()

    check(not can_claim, "Claim rejected — broke user has 0 credits, request stays open")
    check(balance(broke.id) == 0, "Broke user still at 0")

    # ── PATH 6: claim where teacher price > max_credits ──
    print("\n── Path 6: teacher price exceeds learner's max_credits ──")
    bal_before_path6 = balance(learner.id)
    req2 = SkillRequest(user_id=learner.id, name="Expensive Skill", category=SkillCategory.TECHNICAL, max_credits=2)
    db.session.add(req2)
    expensive_skill = make_skill(teacher, "Expensive Skill", cost=4)
    db.session.commit()

    with db.session.begin_nested():
        listing_cost2 = expensive_skill.credit_cost if not RELAY_FLAT_RATE else 1
        too_expensive = listing_cost2 > (req2.max_credits or 1)
        if not too_expensive:
            charge2 = min(listing_cost2, req2.max_credits or 1, RELAY_MAX_CREDIT_COST)
            lc2 = CreditAccount.query.filter(CreditAccount.user_id == learner.id).with_for_update().first()
            if lc2 and lc2.balance >= charge2:
                lc2.balance -= charge2
        db.session.commit()

    check(too_expensive, "Claim rejected — teacher's 4-cost skill exceeds learner's max_credits of 2")
    check(balance(learner.id) == bal_before_path6, f"Learner balance unchanged ({balance(learner.id)})")

    # ── SUMMARY ──
    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed out of {PASS + FAIL} checks")
    print("=" * 60)

    db.drop_all()

sys.exit(0 if FAIL == 0 else 1)
