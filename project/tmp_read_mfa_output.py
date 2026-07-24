from pathlib import Path
path = Path('tmp_mfa_debug_out.txt')
text = path.read_text('utf-16', errors='replace')
for i, line in enumerate(text.splitlines(), start=1):
    if any(tok in line for tok in ['LOGIN', 'SETUP', '400', 'Bad Request', 'ValidationError', 'Invalid', 'Exception', 'MFA']):
        print(f'{i}: {line}')
