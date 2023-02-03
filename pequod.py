#!/usr/bin/env python3
import os
import sys
import time

import argparse
import datetime
import asyncio

component_choices = (
    'example1',
    'example2',

    'all'
)

unique_component_choices = (
    'example1',
    'example2',
)


def mkprint(label=None, file=None):
    if file is None:
        file = sys.stdout

    def _print(s, *args, **kwargs):
        if isinstance(s, bytes):
            s = s.decode('utf-8')
        if label is not None:
            s = '{}: {}'.format(label, s)
        print(s, end='', file=file, *args, **kwargs)

    return _print


async def read_stream(stream, cb):
    while True:
        line = await stream.readline()
        if line:
            cb(line)
        else:
            break


async def stream_subprocess(cmd, stdout_cb, stderr_cb):
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    await asyncio.wait([
        read_stream(process.stdout, stdout_cb),
        read_stream(process.stderr, stderr_cb)
    ])
    return await process.wait()


async def wait_multiple(targets):
    await asyncio.wait(targets)


loop = asyncio.get_event_loop()


def run_external_command(command_args, stdout_cb=None, stderr_cb=None):
    # https://kevinmccarthy.org/2016/07/25/streaming-subprocess-stdin-and-
    # stdout-with-asyncio-in-python/

    rc = loop.run_until_complete(
        stream_subprocess(command_args, stdout_cb, stderr_cb)
    )
    return rc


def run_multiple_commands(commands, stdout_cb=None, stderr_cb=None):
    rc = loop.run_until_complete(
        asyncio.wait([
            stream_subprocess(cmd, stdout_cb, stderr_cb) for cmd in commands]))
    return rc


def run_multiple_command_sets(command_sets):
    rc = loop.run_until_complete(
        asyncio.wait([
            stream_subprocess(cmd, stdout_cb, stderr_cb)
            for cmd, stdout_cb, stderr_cb in command_sets]))
    return rc


def run_multiple_futures(futures):
    rc = loop.run_until_complete(asyncio.wait(futures))
    return rc


def normalize_components(components):
    components = set(components)
    if 'all' in components:
        components = set(unique_component_choices)
    components.discard('all')
    return components


def cmd_build(components):
    components = normalize_components(components)

    command_sets = []

    def build_image(image_name, dockerfile, folder=None):
        if folder is None:
            folder = '.'
        command_sets.append([
            ['docker', 'build', '-t', image_name, '-f', dockerfile, folder],
            mkprint(label=image_name),
            mkprint(label=image_name, file=sys.stderr)])

    if 'example1' in components:
        build_image('example1', 'example1/Dockerfile',
                    'example1')
    if 'example2' in components:
        build_image('example2', 'example2/Dockerfile',
                    'example2')

    run_multiple_command_sets(command_sets)


def cmd_push(components, registry_url, project_name):
    components = normalize_components(components)

    futures = []

    def push_image(image_name):

        stdout = mkprint(label=image_name)
        stderr = mkprint(label=image_name, file=sys.stderr)

        full_image_name = '{}/{}/{}:latest'.format(registry_url, project_name,
                                                   image_name)

        async def tag_and_push():
            await stream_subprocess(
                ['docker', 'tag', image_name, full_image_name], stdout, stderr)
            await stream_subprocess(['docker', 'push', full_image_name],
                                    stdout, stderr)

        futures.append(tag_and_push())

    if 'example1' in components:
        push_image('example1')
    if 'example2' in components:
        push_image('example2')

    run_multiple_futures(futures)


def cmd_build_and_push(components):
    pass


def cmd_login(openshift_url, registry_url, username, password):
    stdout = mkprint("oc login")
    stderr = mkprint("oc login", file=sys.stderr)

    cmd_args = [
        'oc', 'login', openshift_url, '--username={}'.format(username),
        '--password={}'.format(password)
    ]
    run_external_command(cmd_args, stdout_cb=stdout, stderr_cb=stderr)

    token = [None]

    def capture(line):
        token[0] = line.strip()

    run_external_command(['oc', 'whoami', '-t'],
                         stdout_cb=capture,
                         stderr_cb=lambda x: None)

    stdout2 = mkprint("docker login")
    stderr2 = mkprint("docker login", file=sys.stderr)
    cmd_args = ['docker', 'login', '-p', token[0], '-u', 'unused',
                registry_url]
    run_external_command(cmd_args, stdout_cb=stdout2, stderr_cb=stderr2)


def cmd_flake():
    stdout = mkprint("flake")
    stderr = mkprint("flake", file=sys.stderr)

    run_external_command(
        ['flake8', 'example1', 'example2', 'pequod.py'],
        stdout_cb=stdout,
        stderr_cb=stderr)


def cmd_test():
    stdout = mkprint("test")
    stderr = mkprint("test", file=sys.stderr)

    run_external_command(
        ['python', '-m', 'pytest', '--cov=example1', '--cov=example2',
         '--cov=pequod', '--cov-branch', '--cov-report', 'html', 'tests/'],
        stdout_cb=stdout,
        stderr_cb=stderr)


def cmd_diag():
    def get_timestamp():
        dts = datetime.datetime.utcnow()
        epochtime = time.mktime(dts.timetuple()) + dts.microsecond / 1e6
        return epochtime

    def _print(s):
        print('{} -- {}'.format(s, get_timestamp()))

    async def aaa():
        _print('aaa1')
        await asyncio.sleep(1)
        _print('aaa2')
        await bbb()
        _print('aaa3')

    async def bbb():
        _print('bbb1')
        await asyncio.sleep(1)
        _print('bbb2')
        await ccc()
        _print('bbb3')

    async def ccc():
        _print('ccc1')
        await asyncio.sleep(1)
        _print('ccc2')

    loop.run_until_complete(aaa())


def run():
    PEQUOD_REGISTRY_URL = os.getenv('PEQUOD_REGISTRY_URL')
    PEQUOD_PROJECT_NAME = os.getenv('PEQUOD_PROJECT_NAME', 'localhost')
    PEQUOD_OPENSHIFT_URL = os.getenv('PEQUOD_OPENSHIFT_URL')
    PEQUOD_LOGIN_USERNAME = os.getenv('PEQUOD_LOGIN_USERNAME')
    PEQUOD_LOGIN_PASSWORD = os.getenv('PEQUOD_LOGIN_PASSWORD')

    parser = argparse.ArgumentParser()
    # parser.add_argument('cmd', choices=(
    #     'build', 'push', 'bp', 'test', 'flake', 'flake8', 'ci'))

    subs = parser.add_subparsers(dest='command', title='Available commands')

    diag_s = subs.add_parser('diag')
    diag_s.set_defaults(func=lambda _args: cmd_diag())

    def format_envvar(s):
        if s is None:
            return 'unset'
        return '"{}"'.format(s)

    login_s = subs.add_parser('login')
    login_s.add_argument(
        '--openshift-url',
        default=PEQUOD_OPENSHIFT_URL,
        help='The base url for the OpenShift instance that operates the '
             'registry. Usually an HTTPS url. Defaults to the value of the '
             'PEQUOD_OPENSHIFT_URL env var '
             '(currently {}).'.format(format_envvar(PEQUOD_OPENSHIFT_URL)))
    login_s.add_argument(
        '--registry-url',
        default=PEQUOD_REGISTRY_URL,
        help='The base url for the registry to push to. Usually a FQDN. '
             'Defaults to the value of the PEQUOD_REGISTRY_URL env var '
             '(currently {}).'.format(format_envvar(PEQUOD_REGISTRY_URL)))
    login_s.add_argument(
        '--username',
        help='The username to use for logging in. Defaults to the value of '
             'the PEQUOD_LOGIN_USERNAME env var '
             '(currently {}).'.format(format_envvar(PEQUOD_LOGIN_USERNAME)))
    login_s.add_argument(
        '--password',
        help='The password to use for logging in. Defaults to the value of '
             'the PEQUOD_LOGIN_PASSWORD env var '
             '(currently {}).'.format(format_envvar(PEQUOD_LOGIN_PASSWORD)))
    login_s.set_defaults(func=lambda _args: cmd_login(_args.openshift_url,
                                                      _args.registry_url,
                                                      _args.username,
                                                      _args.password))

    build_s = subs.add_parser('build',
                              help='Build one or more component images.')
    build_s.add_argument('components', choices=component_choices, nargs='*')
    build_s.set_defaults(func=lambda _args: cmd_build(_args.components))

    push_s = subs.add_parser(
        'push', help='Push one or more component images to the registry.')
    push_s.add_argument('components', choices=component_choices, nargs='*')
    push_s.add_argument(
        '--registry-url',
        default=PEQUOD_REGISTRY_URL,
        help='The base url for the registry to push to. Usually a FQDN. '
             'Defaults to the value of the PEQUOD_REGISTRY_URL env var '
             '(currently {}).'.format(format_envvar(PEQUOD_REGISTRY_URL)))
    push_s.add_argument(
        '--project-name',
        default=PEQUOD_PROJECT_NAME,
        help='The name of the project/repo to push to. defaults to the value '
             'of the PEQUOD_PROJECT_NAME env var if provided, or else '
             '"localhost" (currently {}).'.format(
                format_envvar(PEQUOD_PROJECT_NAME)))
    push_s.set_defaults(
        func=lambda _args: cmd_push(_args.components, _args.registry_url,
                                    _args.project_name))

    flake_s = subs.add_parser('flake', help='Run flake8 on the source files.')
    flake_s.set_defaults(func=lambda _args: cmd_flake())

    test_s = subs.add_parser('test', help='Run the unit tests.')
    test_s.set_defaults(func=lambda _args: cmd_test())

    args = parser.parse_args()

    if 'func' in args:
        args.func(args)
    else:
        parser.print_help()

    loop.close()


if __name__ == '__main__':
    run()
