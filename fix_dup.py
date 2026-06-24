lines = []
with open('app/main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix first membership/join (line 919): change GET to POST
for i, line in enumerate(lines):
    if i == 918 and 'membership/join' in line:
        lines[i] = line.strip() + ', methods=["POST"]\n'
        break

# Delete lines 932 through 981 (the duplicate monetization section)
# Line 932 = '#  ROUTES: ABOUT...' (end of first section)
# Lines 933-981 = duplicate monetization code 
# Line 982 = '#  ROUTES: ABOUT...' (start of real about section)
del_start = 932
del_end = 981

new_lines = lines[:del_start] + lines[del_end:]

with open('app/main.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("New file: " + str(len(new_lines)) + " lines")
print("membership/join count: " + str(sum(1 for l in new_lines if 'membership/join' in l)))
print("methods=[POST] count: " + str(sum(1 for l in new_lines if 'methods=[\"POST\"]' in l)))
