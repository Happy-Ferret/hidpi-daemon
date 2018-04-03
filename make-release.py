#!/usr/bin/python3

# hidpi-daemon: Universal driver for System76 computers
# Copyright (C) 2005-2016 System76, Inc.
#
# This file is part of `hidpi-daemon`.
#
# `hidpi-daemon` is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# `hidpi-daemon` is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with `hidpi-daemon`; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""
Make a stable hidpi-daemon release.
"""

import sys
import os
from os import path
import re
import time
from subprocess import check_call, check_output, call

from hidpidaemon import __version__
from hidpidaemon.tests.helpers import TempDir


DISTROS = ('trusty', 'xenial', 'yakkety', 'zesty', 'artful', 'bionic')
PPA = 'ppa:system76-dev/pre-stable'
ALPHA = '~alpha'

TREE = path.dirname(path.abspath(__file__))
assert TREE == sys.path[0]
assert os.getcwd() == TREE

CHANGELOG = path.join(TREE, 'debian', 'changelog')
SETUP = path.join(TREE, 'setup.py')
DSC_NAME =     'hidpi-daemon_{}.dsc'.format(__version__)
CHANGES_NAME = 'hidpi-daemon_{}_source.changes'.format(__version__)
PARENT = path.dirname(TREE)
DSC = path.join(PARENT, DSC_NAME)
CHANGES = path.join(PARENT, CHANGES_NAME)

assert path.isfile(CHANGELOG)
assert path.isfile(SETUP)
assert path.isfile(path.join(TREE, 'hidpidaemon', '__init__.py'))


def confirm():
    while True:
        response = input('  Okay? yes/NO: ').lower()
        if response == 'yes':
            return True
        if response == 'no':
            return False
        print("Please enter 'yes' or 'no'")


def check_for_uncommitted_changes():
    if check_output(['git', 'diff']).decode() != '':
        sys.exit('ERROR: unstaged changes!')
    if check_output(['git', 'diff', '--cached']).decode() != '':
        sys.exit('ERROR: uncommited changes!')


def iter_input_lines(fp):
    yield fp.readline()

    line = fp.readline()
    if line != '\n':
        raise ValueError('bad empty line[1]:\n{!r}'.format(line))
    yield line

    line = fp.readline()
    if not line.startswith('  * Daily WIP for '):
        raise ValueError('bad first item line[2]:\n{!r}'.format(line))

    line = fp.readline()
    if line[:4] != '  * ':
        raise ValueError('bad second item line[3]:\n{!r}'.format(line))
    yield line

    i = 4
    while True:
        line = fp.readline()
        if line[:4] not in ('  * ', '    ', '\n'):
            raise ValueError('bad item line[{}]:\n{!r}'.format(i, line))
        yield line
        i += 1
        if line == '\n':
            break

    line = fp.readline()
    if line[:4] != ' -- ':
        raise ValueError('bad author line[{}]:\n{!r}'.format(i, line))
    yield line


def parse_version_line(line):
    if ALPHA not in line:
        raise ValueError('Missing {!r} in version:\n{!r}'.format(ALPHA, line))
    m = re.match(
        '^hidpi-daemon \(([\.0-9]+)~alpha\) ([a-z]+); urgency=low$', line
    )
    if m is None:
        raise ValueError('bad version line[0]:\n{!r}'.format(line))
    ver = m.group(1)
    if ver != __version__:
        raise ValueError(
            'changelog != __version: {!r} != {!r}'.format(ver, __version__)
        )
    distro = m.group(2)
    if distro not in DISTROS:
        raise ValueError('bad distro {!r} not in {!r}'.format(distro, DISTROS))
    return (ver, distro)


def build_version_line(line):
    parse_version_line(line)
    return line.replace('~alpha', '')


def build_author_line():
    author = check_output(['bzr', 'whoami']).decode().strip()
    ts = time.strftime('%a, %d %b %Y %H:%M:%S %z', time.localtime())
    return ' -- {}  {}\n'.format(author, ts)


def iter_output_lines(input_lines):
    yield build_version_line(input_lines[0])
    yield from input_lines[1:-1]
    yield build_author_line()


# Make sure there are no uncommited changes in the tree:
check_for_uncommitted_changes()

# Read lines from current debian/changelog file:
with open(CHANGELOG, 'r') as fp:
    input_lines = list(iter_input_lines(fp))
    remaining_lines = fp.readlines()

# Parse and validate, then build lines for new changelog files:
(version, distro) = parse_version_line(input_lines[0])
assert version == __version__
output_lines = list(iter_output_lines(input_lines))
assert len(output_lines) == len(input_lines)
assert output_lines[1:-1] == input_lines[1:-1]

# Again, make sure there are no uncommited changes in the tree:
check_for_uncommitted_changes()

# Write the new debian/changelog file:
with open(CHANGELOG, 'w') as fp:
    fp.writelines(output_lines + remaining_lines)

# Make sure the unit tests pass in-tree:
check_call([SETUP, 'test'])

# Make sure package builds okay locally using pbuilder-dist:
check_call(['pbuilder-dist', distro, 'update'])
tmp = TempDir()
os.mkdir(tmp.join('result'))
check_call(['dpkg-source', '-b', TREE], cwd=tmp.join('result'))
check_call(['pbuilder-dist', distro, 'build', tmp.join('result', DSC_NAME)])
del tmp

def abort(msg=None):
    if msg is not None:
        print('\nERROR: ' + msg)
    print('')
    print('Release not made, reverting changes...')
    check_call(['git', 'checkout', '--', CHANGELOG, INIT])
    print('Goodbye.')
    status = (0 if msg is None else 2)
    sys.exit(status)

# Confirm before we make the commit:
print('-' * 80)
call(['git', 'diff'])
print('-' * 80)
print('Source tree is {!r}'.format(TREE))
print('Will release {!r} for {!r}'.format(version, distro))
if not confirm():
    abort()

# Make sure DSC and CHANGES file for this version don't arleady exist:
for filename in (DSC, CHANGES):
    if path.isfile(filename):
        abort('Already exists: {!r}'.format(filename))

# Commit and tag:
check_call(['git', 'commit', CHANGELOG, '-m', 'Release {}'.format(version)])
check_call(['git', 'push'])
check_call(['git', 'tag', version])
check_call(['git', 'push', 'origin', 'tag', version])

# Build source package:
check_call(['gbp', 'buildpackage', '--git-ignore-branch', '-S'])

# Confirm before we dput to PPA:
print('-' * 80)
print('Changes file is {!r}'.format(CHANGES))
print('Will upload to {!r}'.format(PPA))
if confirm():
    check_call(['dput', PPA, CHANGES])

# We're done:
print('-' * 80)
print('Released {!r} for {!r}'.format(version, distro))
