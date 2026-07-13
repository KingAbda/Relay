import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ['RELAY_SECRET_KEY'] = 'temp'
os.environ['DATABASE_URL'] = 'sqlite:///app/instance/relay.db'

from app.main import app, db
from app.models import CreditAccount, CreditTransaction, TransactionType

with app.app_context():
    # Find all bonus transactions that were starter credits
    starters = CreditTransaction.query.filter(
        CreditTransaction.type == TransactionType.BONUS,
        CreditTransaction.description.like('%free credits to start%')
    ).all()
    
    fixed = 0
    for tx in starters:
        # The user got DOUBLE: balance was set to N, then add_credit_transaction added N more
        # Fix: subtract N from their balance (the amount that was double-counted)
        account = CreditAccount.query.filter(CreditAccount.user_id == tx.user_id).first()
        if account:
            # If balance is >= the starter amount, it was double-counted
            if account.balance >= tx.amount:
                account.balance -= tx.amount
                fixed += 1
    
    db.session.commit()
    print(f"Fixed {fixed} accounts. Each had balance reduced by starter credit amount.")
    print("New accounts will correctly start at the configured amount.")
