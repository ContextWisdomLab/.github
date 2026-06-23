import sys

with open('scripts/ci/pr_review_merge_scheduler.py', 'r') as f:
    lines = f.readlines()

new_lines = []
in_conflict = False
for line in lines:
    if line.startswith('<<<<<<< HEAD'):
        in_conflict = True
    elif line.startswith('======='):
        pass
    elif line.startswith('>>>>>>> origin/main'):
        in_conflict = False
    elif in_conflict:
        pass
    else:
        new_lines.append(line)

for i, line in enumerate(new_lines):
    if line.strip() == 'process = subprocess.run(args, input=stdin, capture_output=True, text=True)':
        new_lines[i] = '    process = subprocess.run(args, input=stdin, capture_output=True, text=True, shell=False, check=False)\n'
    elif 'def run(args: list[str], *, stdin: str | None = None) -> str:' in line:
        new_lines.insert(i+1, '    """Run a command and return stdout, raising with stderr on failure."""\n')

with open('scripts/ci/pr_review_merge_scheduler.py', 'w') as f:
    f.writelines(new_lines)
