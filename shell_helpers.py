#!/usr/bin/env python3

import distutils.file_util
import itertools
import os
import shlex
import shutil
import signal
import subprocess

class LF:
    '''
    LineFeed (AKA newline).

    Singleton class. Can be used in print_cmd to print out nicer command lines
    with --key on the same line as "--key value".
    '''
    pass

class ShellHelpers:
    '''
    Helpers to do things which are easy from the shell,
    usually filesystem, process or pipe operations.

    Attempt to print shell equivalents of all commands to make things
    easy to debug and understand what is going on.
    '''
    def __init__(self, dry_run=False):
        '''
        :param dry_run: don't run the commands, just potentially print them. Debug aid.
        :type dry_run: Bool
        '''
        self.dry_run = dry_run

    def add_newlines(self, cmd):
        out = []
        for arg in cmd:
            out.extend([arg, LF])
        return out

    def cp(self, src, dest, **kwargs):
        self.print_cmd(['cp', src, dest])
        if not self.dry_run:
            shutil.copy2(src, dest)

    def cmd_to_string(self, cmd, cwd=None, extra_env=None, extra_paths=None):
        '''
        Format a command given as a list of strings so that it can
        be viewed nicely and executed by bash directly and print it to stdout.
        '''
        last_newline = ' \\\n'
        newline_separator = last_newline + '  '
        out = []
        if extra_env is None:
            extra_env = {}
        if cwd is not None:
            out.append('cd {} &&'.format(shlex.quote(cwd)))
        if extra_paths is not None:
            out.append('PATH="{}:${{PATH}}"'.format(':'.join(extra_paths)))
        for key in extra_env:
            out.append('{}={}'.format(shlex.quote(key), shlex.quote(extra_env[key])))
        cmd_quote = []
        newline_count = 0
        for arg in cmd:
            if arg == LF:
                cmd_quote.append(arg)
                newline_count += 1
            else:
                cmd_quote.append(shlex.quote(arg))
        if newline_count > 0:
            cmd_quote = [' '.join(list(y)) for x, y in itertools.groupby(cmd_quote, lambda z: z == LF) if not x]
        out.extend(cmd_quote)
        if newline_count == 1 and cmd[-1] == LF:
            ending = ''
        else:
            ending = last_newline + ';'
        return newline_separator.join(out) + ending

    def copy_dir_if_update_non_recursive(self, srcdir, destdir, filter_ext=None):
        # TODO print rsync equivalent.
        os.makedirs(destdir, exist_ok=True)
        for basename in os.listdir(srcdir):
            src = os.path.join(srcdir, basename)
            if os.path.isfile(src):
                noext, ext = os.path.splitext(basename)
                if filter_ext is not None and ext == filter_ext:
                    distutils.file_util.copy_file(
                        src,
                        os.path.join(destdir, basename),
                        update=1,
                    )

    def print_cmd(self, cmd, cwd=None, cmd_file=None, extra_env=None, extra_paths=None):
        '''
        Print cmd_to_string to stdout.

        Optionally save the command to cmd_file file, and add extra_env
        environment variables to the command generated.

        If cmd contains at least one LF, newlines are only added on LF.
        Otherwise, newlines are added automatically after every word.
        '''
        if type(cmd) is str:
            cmd_string = cmd
        else:
            cmd_string = self.cmd_to_string(cmd, cwd=cwd, extra_env=extra_env, extra_paths=extra_paths)
        print('+ ' + cmd_string)
        if cmd_file is not None:
            with open(cmd_file, 'w') as f:
                f.write('#!/usr/bin/env bash\n')
                f.write(cmd_string)
            st = os.stat(cmd_file)
            os.chmod(cmd_file, st.st_mode | stat.S_IXUSR)

    def run_cmd(
            self,
            cmd,
            cmd_file=None,
            out_file=None,
            show_stdout=True,
            show_cmd=True,
            extra_env=None,
            extra_paths=None,
            delete_env=None,
            raise_on_failure=True,
            **kwargs
        ):
        '''
        Run a command. Write the command to stdout before running it.

        Wait until the command finishes execution.

        :param cmd: command to run. LF entries are magic get skipped.
        :type cmd: List[str]

        :param cmd_file: if not None, write the command to be run to that file
        :type cmd_file: str

        :param out_file: if not None, write the stdout and stderr of the command the file
        :type out_file: str

        :param show_stdout: wether to show stdout and stderr on the terminal or not
        :type show_stdout: bool

        :param extra_env: extra environment variables to add when running the command
        :type extra_env: Dict[str,str]
        '''
        if out_file is not None:
            stdout = subprocess.PIPE
            stderr = subprocess.STDOUT
        else:
            if show_stdout:
                stdout = None
                stderr = None
            else:
                stdout = subprocess.DEVNULL
                stderr = subprocess.DEVNULL
        if extra_env is None:
            extra_env = {}
        if delete_env is None:
            delete_env = []
        if 'cwd' in kwargs:
            cwd = kwargs['cwd']
        else:
            cwd = None
        env = os.environ.copy()
        env.update(extra_env)
        if extra_paths is not None:
            path = ':'.join(extra_paths)
            if 'PATH' in os.environ:
                path += ':' + os.environ['PATH']
            env['PATH'] = path
        for key in delete_env:
            if key in env:
                del env[key]
        if show_cmd:
            self.print_cmd(cmd, cwd=cwd, cmd_file=cmd_file, extra_env=extra_env, extra_paths=extra_paths)

        # Otherwise Ctrl + C gives:
        # - ugly Python stack trace for gem5 (QEMU takes over terminal and is fine).
        # - kills Python, and that then kills GDB: https://stackoverflow.com/questions/19807134/does-python-always-raise-an-exception-if-you-do-ctrlc-when-a-subprocess-is-exec
        sigint_old = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        # Otherwise BrokenPipeError when piping through | grep
        # But if I do this_module, my terminal gets broken at the end. Why, why, why.
        # https://stackoverflow.com/questions/14207708/ioerror-errno-32-broken-pipe-python
        # Ignoring the exception is not enough as it prints a warning anyways.
        #sigpipe_old = signal.getsignal(signal.SIGPIPE)
        #signal.signal(signal.SIGPIPE, signal.SIG_DFL)

        cmd = self.strip_newlines(cmd)
        if not self.dry_run:
            # https://stackoverflow.com/questions/15535240/python-popen-write-to-stdout-and-log-file-simultaneously/52090802#52090802
            with subprocess.Popen(cmd, stdout=stdout, stderr=stderr, env=env, **kwargs) as proc:
                if out_file is not None:
                    os.makedirs(os.path.split(os.path.abspath(out_file))[0], exist_ok=True)
                    with open(out_file, 'bw') as logfile:
                        while True:
                            byte = proc.stdout.read(1)
                            if byte:
                                if show_stdout:
                                    sys.stdout.buffer.write(byte)
                                    try:
                                        sys.stdout.flush()
                                    except BlockingIOError:
                                        # TODO understand. Why, Python, why.
                                        pass
                                logfile.write(byte)
                            else:
                                break
            signal.signal(signal.SIGINT, sigint_old)
            #signal.signal(signal.SIGPIPE, sigpipe_old)
            returncode = proc.returncode
            if returncode != 0 and raise_on_failure:
                raise Exception('Command exited with status: {}'.format(returncode))
            return returncode
        else:
            return 0

    def shlex_split(self, string):
        '''
        shlex_split, but also add Newline after every word.

        Not perfect since it does not group arguments, but I don't see a solution.
        '''
        return self.add_newlines(shlex.split(string))

    def strip_newlines(self, cmd):
        return [x for x in cmd if x != LF]

    def rmrf(path):
        self.print_cmd(['rm', '-r', '-f', path])
        if not self.dry_run and os.path.exists(path):
            shutil.rmtree(path)

    def write_configs(self, config_path, configs, config_fragments=None):
        '''
        Write extra KEY=val configs into the given config file.
        '''
        if config_fragments is None:
            config_fragments = []
        with open(config_path, 'a') as config_file:
            for config_fragment in config_fragments:
                with open(config_fragment, 'r') as config_fragment_file:
                    self.print_cmd(['cat', config_fragment, '>>', config_path])
                    if not self.dry_run:
                        for line in config_fragment_file:
                            config_file.write(line)
        write_string_to_file(config_path, '\n'.join(configs), mode='a')

    def write_string_to_file(self, path, string, mode='w'):
        if mode == 'a':
            redirect = '>>'
        else:
            redirect = '>'
        self.print_cmd("cat << 'EOF' {} {}\n{}\nEOF".format(redirect, path, string))
        if not self.dry_run:
            with open(path, 'a') as f:
                f.write(string)
