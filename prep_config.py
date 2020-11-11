import os
import random
import string

random_string_marker = '[Random String Here]'


def random_string():
    character_set = string.ascii_lowercase + string.ascii_uppercase + string.digits
    return ''.join(random.choice(character_set) for _ in range(32))


if not os.path.exists('settings'):
    print('creating settings folder')
    os.mkdir('settings')
if not os.path.exists('settings/config.py'):
    print('copying settings file')

    with open('sample_settings/config.py') as sample:
        with open('settings/config.py', 'w') as copy:
            for line in sample.readlines():
                if random_string_marker in line:
                    line = line.replace(random_string_marker, random_string())
                copy.write(line)
