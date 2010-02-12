# Verify that systemtap static probes work
#
import subprocess
import sys
import sysconfig
import os
import unittest

from test.support import run_unittest, TESTFN, unlink

if '--with-systemtap' not in sysconfig.get_config_var('CONFIG_ARGS'):
    raise unittest.SkipTest("Python was not configured --with-systemtap")

try:
    _, stap_version = subprocess.Popen(["stap", "-V"],
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       ).communicate()
except OSError:
    # This is what "no stap" looks like.  There may, however, be other
    # errors that manifest this way too.
    raise unittest.SkipTest("Couldn't find stap on the path")

def invoke_systemtap_script(script, cmd):
    # Start a child process, probing with the given systemtap script
    # (passed as stdin to the "stap" tool)
    # The script should be a bytes instance
    # Return (stdout, stderr) pair

    p = subprocess.Popen(["stap", "-", '-vv', '-c', cmd],
                         stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    out, err = p.communicate(input=script)
    return out, err

# Verify that stap can run a simple "hello world"-style script
# This can fail for various reasons:
# - missing kernel headers
# - permissions (a non-root user needs to be in the "stapdev" group)
TRIVIAL_STAP_SCRIPT = b'probe begin { println("hello world") exit () }'

out, err = invoke_systemtap_script(TRIVIAL_STAP_SCRIPT, 'true')
if out != b'hello world\n':
    raise unittest.SkipTest("Test systemtap script did not run; stderr was: %s" % err)

# We don't expect stderr to be empty, since we're invoking stap with "-vv": stap
# will (we hope) generate debugging output on stderr.

def invoke_python_under_systemtap(script, pythoncode=None, pythonfile=None):
    # Start a child python process, probing with the given systemtap script
    # (passed as stdin to the "stap" tool)
    # The script should be a bytes instance
    # Return (stdout, stderr) pair

    if pythonfile:
        pythoncmd = '%s %s' % (sys.executable, pythonfile)
    else:
        pythoncmd = '%s -c %r' % (sys.executable, pythoncode)

    # The process tree of a stap invocation of a command goes through
    # something like this:
    #    stap ->fork/exec(staprun; exec stapio ->f/e(-c cmd); exec staprun -r)
    # and this trip through setuid leads to LD_LIBRARY_PATH being dropped,
    # which would lead to an --enable-shared build of python failing to be
    # find its libpython, with an error like:
    #    error while loading shared libraries: libpython3.3dm.so.1.0: cannot
    #    open shared object file: No such file or directory
    # Hence we need to jump through some hoops to expose LD_LIBRARY_PATH to
    # the invoked python process:
    LD_LIBRARY_PATH = os.environ.get('LD_LIBRARY_PATH', '')
    if LD_LIBRARY_PATH:
        pythoncmd = 'env LD_LIBRARY_PATH=%s ' % LD_LIBRARY_PATH + pythoncmd

    return invoke_systemtap_script(script, pythoncmd)

# When using the static markers, we need to supply the prefix of a systemtap
# dotted probe point that containing the marker.
# See http://sourceware.org/systemtap/langref/Probe_points.html
#
# We need to determine if this is a shared-library build
#
# Note that sysconfig can get this wrong; see:
#   http://bugs.python.org/issue14774
#
if '--enable-shared' in sysconfig.get_config_var('CONFIG_ARGS'):
    # For a shared-library build, the markers are in library(INSTSONAME):
    INSTSONAME = sysconfig.get_config_var('INSTSONAME')
    probe_prefix = 'process("%s").library("%s")' % (sys.executable, INSTSONAME)
else:
    # For a non-shared-library build, we can simply use sys.executable:
    probe_prefix = 'process("%s")' % sys.executable

# The following script ought to generate lots of lines showing recursive
# function entry and return, of the form:
#     11408 python(8274):        => __contains__ in Lib/_abcoll.py:362
#     11414 python(8274):         => __getitem__ in Lib/os.py:425
#     11418 python(8274):          => encode in Lib/os.py:490
#     11424 python(8274):          <= encode in Lib/os.py:493
#     11428 python(8274):         <= __getitem__ in Lib/os.py:426
#     11433 python(8274):        <= __contains__ in Lib/_abcoll.py:366
# where the column are:
#  - time in microseconds since start of script
#  - name of executable
#  - PID of process
#  and the remainder indicates the call/return hierarchy

hierarchy_script = ('''
probe %s.mark("function__entry") {
    filename = user_string($arg1);
    funcname = user_string($arg2);
    lineno = $arg3;

    printf("%%s => %%s in %%s:%%d\\n", thread_indent(1), funcname, filename, lineno);
}

probe %s.mark("function__return") {
    filename = user_string($arg1);
    funcname = user_string($arg2);
    lineno = $arg3;

    printf("%%s <= %%s in %%s:%%d\\n", thread_indent(-1), funcname, filename, lineno);
}
''' % (probe_prefix, probe_prefix)).encode('utf-8')


class ErrorDumper:
    # A context manager that dumps extra information if an exception is raised,
    # to help track down why the problem occurred
    def __init__(self, out, err):
        self.out = out
        self.err = err

    def __enter__(self):
        pass

    def __exit__(self, type_, value, traceback):
        if type_:
            # an exception is being raised:
            print('stdout: %s' % out.decode())
            print('stderr: %s' % err.decode())

class SystemtapTests(unittest.TestCase):

    def test_invoking_python(self):
        # Ensure that we can invoke python under stap, with a trivial stap
        # script:
        out, err = invoke_python_under_systemtap(
            b'probe begin { println("hello from stap") exit () }',
            pythoncode="print('hello from python')")
        with ErrorDumper(out, err):
            self.assertIn(b'hello from stap', out)
            self.assertIn(b'hello from python', out)

    def test_function_entry(self):
        # Ensure that the function_entry static marker works
        out, err = invoke_python_under_systemtap(hierarchy_script)
        # stdout ought to contain various lines showing recursive function
        # entry and return (see above)

        # Uncomment this for debugging purposes:
        # print(out.decode('utf-8'))

        #   Executing the cmdline-supplied "pass":
        #      0 python(8274): => <module> in <string>:1
        #      5 python(8274): <= <module> in <string>:1
        with ErrorDumper(out, err):
            self.assertIn(b'=> <module> in <string>:1', out,
                          msg="stdout: %s\nstderr: %s\n" % (out, err))

    def test_function_encoding(self):
        # Ensure that function names containing non-Latin 1 code
        # points are handled:
        pythonfile = TESTFN
        try:
            unlink(pythonfile)
            f = open(pythonfile, "wb")
            f.write("""
# Sample script with non-ASCII filename, for use by test_systemtap.py
# Implicitly UTF-8

def 文字化け():
    '''Function with non-ASCII identifier; I believe this reads "mojibake"'''
    print("hello world!")

文字化け()
""".encode('utf-8'))
            f.close()

            out, err = invoke_python_under_systemtap(hierarchy_script,
                                                     pythonfile=pythonfile)
            out_utf8 = out.decode('utf-8')
            with ErrorDumper(out, err):
                self.assertIn('=> <module> in %s:5' % pythonfile, out_utf8)
                self.assertIn(' => 文字化け in %s:5' % pythonfile, out_utf8)
                self.assertIn(' <= 文字化け in %s:7' % pythonfile, out_utf8)
                self.assertIn('<= <module> in %s:9' % pythonfile, out_utf8)
        finally:
            unlink(pythonfile)

    @unittest.skipIf(sys.getfilesystemencoding() == 'ascii',
                     'the test filename is not encodable with ASCII')
    def test_filename_encoding(self):
        # Ensure that scripts names containing non-Latin 1 code
        # points are handled:
        pythonfile = TESTFN + '_☠.py'
        try:
            unlink(pythonfile)
            f = open(pythonfile, "wb")
            f.write("""
def foo():
    '''Function with non-ASCII identifier; I believe this reads "mojibake"'''
    print("hello world!")

foo()
""".encode('utf-8'))
            f.close()

            out, err = invoke_python_under_systemtap(hierarchy_script,
                                                     pythonfile=pythonfile)
            out_utf8 = out.decode('utf-8')
            with ErrorDumper(out, err):
                self.assertIn('=> <module> in %s:2' % pythonfile, out_utf8)
                self.assertIn(' => foo in %s:2' % pythonfile, out_utf8)
                self.assertIn(' <= foo in %s:4' % pythonfile, out_utf8)
                self.assertIn('<= <module> in %s:6' % pythonfile, out_utf8)
        finally:
            unlink(pythonfile)

def test_main():
    run_unittest(SystemtapTests)

if __name__ == "__main__":
    test_main()
