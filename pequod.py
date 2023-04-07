#!/usr/bin/env python3

"""
Build container images of the various components and push them to a registry.
"""

from datetime import datetime
from io import BytesIO, StringIO
from itertools import chain
import subprocess

import os
import sys

import argparse
import asyncio


def get_image_tag_from_git_commit():
    describe_args = ['git', 'describe', '--exclude=*', '--always',
                     '--abbrev=40', '--dirty']
    p = subprocess.run(describe_args, stdout=subprocess.PIPE)
    tag = p.stdout.decode('utf-8').strip()
    if tag.endswith('-dirty'):
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        tag = f'{tag}-{timestamp}'
    return tag


DEFAULT_IMAGE_TAG = get_image_tag_from_git_commit()


def run(config):
    PEQUOD_REGISTRY_URL = os.getenv('PEQUOD_REGISTRY_URL')
    PEQUOD_PROJECT_NAME = os.getenv('PEQUOD_PROJECT_NAME', 'localhost')
    PEQUOD_OPENSHIFT_URL = os.getenv('PEQUOD_OPENSHIFT_URL')
    PEQUOD_LOGIN_USERNAME = os.getenv('PEQUOD_LOGIN_USERNAME')
    PEQUOD_LOGIN_PASSWORD = os.getenv('PEQUOD_LOGIN_PASSWORD')

    PEQUOD_POST_COMMAND = os.getenv('PEQUOD_POST_COMMAND')

    parser = argparse.ArgumentParser()

    subs = parser.add_subparsers(dest='command', title='Available commands')

    def format_envvar(s):
        if s is None:
            return 'unset'
        return '"{}"'.format(s)

    # login_s = subs.add_parser('login')
    # login_s.add_argument(
    #     '--openshift-url',
    #     default=PEQUOD_OPENSHIFT_URL,
    #     help='The base url for the OpenShift instance that operates the '
    #          'registry. Usually an HTTPS url. Defaults to the value of the '
    #          'PEQUOD_OPENSHIFT_URL env var '
    #          '(currently {}).'.format(format_envvar(PEQUOD_OPENSHIFT_URL)))
    # login_s.add_argument(
    #     '--registry-url',
    #     default=PEQUOD_REGISTRY_URL,
    #     help='The base url for the registry to push to. Usually a FQDN. '
    #          'Defaults to the value of the PEQUOD_REGISTRY_URL env var '
    #          '(currently {}).'.format(format_envvar(PEQUOD_REGISTRY_URL)))
    # login_s.add_argument(
    #     '--username',
    #     help='The username to use for logging in. Defaults to the value of '
    #          'the PEQUOD_LOGIN_USERNAME env var '
    #          '(currently {}).'.format(format_envvar(PEQUOD_LOGIN_USERNAME)))
    # login_s.add_argument(
    #     '--password',
    #     help='The password to use for logging in. Defaults to the value of '
    #          'the PEQUOD_LOGIN_PASSWORD env var '
    #          '(currently {}).'.format(format_envvar(PEQUOD_LOGIN_PASSWORD)))
    # login_s.add_argument(
    #     '--password-stdin', action='store_true',
    #     help='Take the password to use for logging in from STDIN.')
    #
    # login_s.set_defaults(func=lambda _args: cmd_login(_args.openshift_url,
    #                                                   _args.registry_url,
    #                                                   _args.username,
    #                                                   _args.password,
    #                                                   _args.password_stdin),
    #                      on_post='login complete')

    build_s = subs.add_parser('build',
                              help='Build one or more component images.')
    build_s.add_argument('components', choices=component_choices, nargs='*')
    build_s.add_argument(
        '--version-tag',
        default=DEFAULT_IMAGE_TAG,
        help=f'A value to set as the VERSION_TAG build argument when running'
             f' `docker build` Changing this is not recommended. Defaults to'
             f' a string based on the current time and git commit description'
             f' ("{DEFAULT_IMAGE_TAG}").')
    build_s.set_defaults(func=cmd_build,
                         on_post='build complete')

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
    push_s.add_argument(
        '--image-tag',
        default=DEFAULT_IMAGE_TAG,
        help='The tag for the docker image, e.g. "1.0" or "2.3.4-rev5-alpha" '
             'or "stable" or "latest". Defaults to a string based on the '
             'current time and git commit description.')
    push_s.set_defaults(
        func=cmd_push,
        on_post='push complete')

    bp_s = subs.add_parser(
        'bp', help='Both build and push selected component images')
    bp_s.add_argument('components', choices=component_choices, nargs='*')
    bp_s.add_argument(
        '--registry-url',
        default=PEQUOD_REGISTRY_URL,
        help='The base url for the registry to push to. Usually a FQDN. '
             'Defaults to the value of the PEQUOD_REGISTRY_URL env var '
             '(currently {}).'.format(format_envvar(PEQUOD_REGISTRY_URL)))
    bp_s.add_argument(
        '--project-name',
        default=PEQUOD_PROJECT_NAME,
        help='The name of the project/repo to push to. defaults to the value '
             'of the PEQUOD_PROJECT_NAME env var if provided, or else '
             '"localhost" (currently {}).'.format(
            format_envvar(PEQUOD_PROJECT_NAME)))
    bp_s.add_argument(
        '--image-tag',
        default=DEFAULT_IMAGE_TAG,
        help='The tag for the docker image, e.g. "1.0" or "2.3.4-rev5-alpha" '
             'or "stable" or "latest". Defaults to a string based on the '
             'current time and git commit description.')
    bp_s.set_defaults(func=cmd_build_and_push,
                      on_post='build and push complete')

    flake_s = subs.add_parser('flake', help='Run flake8 on the source files.')
    # TODO: specify components
    flake_s.set_defaults(func=lambda _args: cmd_flake(),
                         on_post='flake 8 complete')

    test_s = subs.add_parser('test', help='Run the unit tests.')
    # TODO: specify components
    test_s.set_defaults(func=lambda _args: cmd_test(),
                        on_post='unit tests complete')

    info_s = subs.add_parser(
        'info',
        help='Display info about the configured components.')
    info_s.set_defaults(func=cmd_info)

    args = parser.parse_args()

    if 'func' in args:
        kwargs = vars(args)
        args.func(**kwargs)
        if PEQUOD_POST_COMMAND and 'on_post' in args and args.on_post:
            cmd = PEQUOD_POST_COMMAND.split() + args.on_post.split()
            run_external_command(cmd, print, print)
    else:
        parser.print_help()

    loop.close()


def cmd_build(components, **kwargs):
    components = normalize_components(components)
    futures = []
    for comp in components:
        if not comp.is_supported:
            print("{} is not currently supported".format(comp.name))
            continue
        futures.append(build_image(comp))
    run_multiple_futures(futures)


def cmd_push(components, registry_url, project_name, image_tag, **kwargs):
    components = normalize_components(components)
    futures = []
    for comp in components:
        if not comp.is_supported:
            print("{} is not currently supported".format(comp.name))
            continue
        futures.append(tag_and_push_image(comp, registry_url,
                                          project_name, image_tag))
    run_multiple_futures(futures)


def cmd_build_and_push(components, registry_url, project_name, image_tag,
                       **kwargs):
    components = normalize_components(components)
    futures = []
    for comp in components:
        if not comp.is_supported:
            print("{} is not currently supported".format(comp.name))
            continue
        futures.append(build_and_tag_and_push_image(comp, registry_url,
                                                    project_name, image_tag))
    run_multiple_futures(futures)


def cmd_login(openshift_url, registry_url, username, password,
              password_stdin, **kwargs):
    if not password and password_stdin:
        password = sys.stdin.read().splitlines()[0]

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


def cmd_flake(**kwargs):
    stdout = mkprint("flake")
    stderr = mkprint("flake", file=sys.stderr)

    run_external_command(
        ['flake8', 'example1', 'example2', 'pequod.py'],
        stdout_cb=stdout,
        stderr_cb=stderr)


def cmd_test(**kwargs):
    stdout = mkprint("test")
    stderr = mkprint("test", file=sys.stderr)

    run_external_command(
        ['python', '-m', 'pytest', '--cov=example1', '--cov=example2',
         '--cov=pequod', '--cov-branch', '--cov-report', 'html', 'tests/'],
        stdout_cb=stdout,
        stderr_cb=stderr)


def cmd_info(*args, **kwargs):
    components = set(_ for _ in component_items_by_name.values()
                     if isinstance(_, Component))
    components = list(sorted(components, key=lambda _: _.name))
    groups = set(_ for _ in component_items_by_name.values()
                 if isinstance(_, ComponentGroup))
    groups = list(sorted(groups, key=lambda _: _.name))
    if not components:
        print('No configured components')
    else:
        print('Components:')
        for c in components:
            print(f'  {c.name}')
            # TODO: print info like type, aliases, depends_on
    print('')
    if not groups:
        print('No groups')
    else:
        print('Groups:')
        for g in groups:
            print(f'  {g.name}')
            # TODO: print group contents, aliases


class Component:
    def __init__(self, name, image_name, dockerfile, comp_type=None,
                 context_folder=None, aliases=None, depends_on=None):
        self.name = name
        self.image_name = image_name
        self.dockerfile = dockerfile
        self.comp_type = comp_type
        if context_folder is None:
            context_folder = '.'
        self.context_folder = context_folder
        if aliases is None:
            aliases = []
        self.aliases = list(aliases)
        self.is_supported = True
        if depends_on is None:
            depends_on = []
        if not isinstance(depends_on, (list, tuple)):
            depends_on = [depends_on]
        if isinstance(depends_on, tuple):
            depends_on = list(depends_on)
        self.depends_on = depends_on

    def __repr__(self):
        return 'Component(\'{}\')'.format(self.name)

    def get_components(self):
        return [self]


class ComponentGroup:
    def __init__(self, name, includes, aliases=None):
        self.name = name
        self.includes = list(includes)
        if aliases is None:
            aliases = []
        self.aliases = list(aliases)

    def __repr__(self):
        return 'ComponentGroup(\'{}\')'.format(self.name)

    def get_components(self):
        return [comp
                for item in self.includes
                for comp in item.get_components()]


def load_config_file(conf_file=None):
    if conf_file is None:
        conf_file = 'pequod.yaml'
    import yaml
    with open(conf_file) as f:
        return yaml.load(f, Loader=yaml.Loader)


def load_components(config):
    if 'components' not in config:
        raise Exception("No components defined")
    # TODO: depends_on
    components = []
    components_by_type = {}
    for c in config['components']:
        # TODO: check arguments
        # TODO: link strings to Component objects
        cc = Component(**c)
        components.append(cc)
        if cc.comp_type:
            if cc.comp_type not in components_by_type:
                components_by_type[cc.comp_type] = []
            components_by_type[cc.comp_type].append(cc)
    groups = []
    groups_by_name = {}
    if 'groups' in config:
        for g in config['groups']:
            # TODO: check arguments
            # TODO: link strings to Component and ComponentGroup objects
            gg = ComponentGroup(**g)
            groups_by_name[gg.name] = gg
            groups.append(gg)
    if 'all' not in groups_by_name:
        all_group = ComponentGroup('all', components)
        groups_by_name['all'] = all_group
        groups.append(all_group)
    for comp_type, comps in components_by_type.items():
        if comp_type not in groups_by_name:
            g = ComponentGroup(name=comp_type, includes=comps)
            groups.append(g)
            groups_by_name[comp_type] = g

    items_by_name = {}
    for c in components:
        # TODO: don't overwrite duplicate keys?
        items_by_name[c.name] = c
        for a in c.aliases:
            items_by_name[a] = c
    for g in groups:
        # TODO: don't overwrite duplicate keys?
        items_by_name[g.name] = g
        for a in g.aliases:
            items_by_name[a] = g

    return items_by_name


config = load_config_file()
component_items_by_name = load_components(config)
component_choices = sorted(component_items_by_name.keys())


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


async def write_stream(stream, cb):
    if cb is None:
        return
    while True:
        line = cb()
        if line:
            await stream.writeline()
        else:
            break


async def stream_subprocess(cmd, stdout_cb, stderr_cb, stdin_cb=None):
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    awaitables = [
        read_stream(process.stdout, stdout_cb),
        read_stream(process.stderr, stderr_cb),
    ]
    if stdin_cb:
        awaitables.append(write_stream(process.stdin, stdin_cb))
    await asyncio.wait(awaitables)
    return await process.wait()


async def wait_multiple(targets):
    await asyncio.wait(targets)


loop = asyncio.get_event_loop()


def run_external_command(command_args, stdout_cb=None, stderr_cb=None,
                         stdin=None):
    # https://kevinmccarthy.org/2016/07/25/streaming-subprocess-stdin-and-
    # stdout-with-asyncio-in-python/

    if isinstance(stdin, bytes):
        stdin = BytesIO(stdin).readline
    if isinstance(stdin, str):
        stdin = StringIO(stdin).readline

    rc = loop.run_until_complete(
        stream_subprocess(command_args, stdout_cb, stderr_cb, stdin_cb=stdin)
    )
    return rc


def run_multiple_futures(futures):
    rc = loop.run_until_complete(asyncio.wait(futures))
    return rc


def compose_image_operation_command(comp, registry_url=None, project_name=None,
                                    build=False, push=False, image_tag=None):
    stdout = mkprint(label=comp.image_name)
    stderr = mkprint(label=comp.image_name, file=sys.stderr)
    if image_tag is None:
        image_tag = DEFAULT_IMAGE_TAG
    full_image_name = '{}/{}/{}:{}'.format(registry_url, project_name,
                                           comp.image_name, image_tag)
    if build and push:
        async def _build_and_tag_and_push():
            await stream_subprocess(
                ['docker', 'build', '-t', comp.image_name, '-f',
                 comp.dockerfile, comp.context_folder],
                stdout, stderr)
            await stream_subprocess(
                ['docker', 'tag', comp.image_name, full_image_name],
                stdout, stderr)
            await stream_subprocess(['docker', 'push', full_image_name],
                                    stdout, stderr)

        return _build_and_tag_and_push()
    elif build:
        async def _build():
            await stream_subprocess(
                ['docker', 'build', '-t', comp.image_name, '-f',
                 comp.dockerfile, comp.context_folder],
                stdout, stderr)

        return _build()
    elif push:
        async def _tag_and_push():
            await stream_subprocess(
                ['docker', 'tag', comp.image_name, full_image_name],
                stdout, stderr)
            await stream_subprocess(['docker', 'push', full_image_name],
                                    stdout, stderr)

        return _tag_and_push()
    else:
        raise Exception('Invalid operation, neither build nor push')


def build_image(comp):
    return compose_image_operation_command(comp, build=True, push=False)


def tag_and_push_image(comp, registry_url, project_name, image_tag):
    return compose_image_operation_command(
        comp, registry_url=registry_url, project_name=project_name,
        build=False, push=True, image_tag=image_tag)


def build_and_tag_and_push_image(comp, registry_url, project_name, image_tag):
    return compose_image_operation_command(
        comp, registry_url=registry_url, project_name=project_name,
        build=True, push=True, image_tag=image_tag)


def normalize_components(component_names):
    items = {component_items_by_name[name] for name in component_names}
    return list(chain(*(item.get_components() for item in items)))


if __name__ == '__main__':
    run(config)
