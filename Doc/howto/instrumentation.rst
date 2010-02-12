.. _instrumentation:

====================================
Instrumenting CPython with SystemTap
====================================

:author: David Malcolm <dmalcolm@redhat.com>

DTrace and SystemTap are monitoring tools, each providing a way to inspect
what the processes on a computer system are doing.  They both use
domain-specific languages allowing a user to write scripts which:

  - filter which processes are to be observed
  - gather data from the processes of interest
  - generate reports on the data

As of Python 3.3, CPython can be built with embedded "markers" that can be
observed by a SystemTap script, making it easier to monitor what the CPython
processes on a system are doing.

.. Potentially this document could be expanded to also cover DTrace markers.
   However, I'm not a DTrace expert.

.. I'm using ".. code-block:: c" for SystemTap scripts, as "c" is syntactically
   the closest match that Sphinx supports


Enabling the static markers
---------------------------

In order to build CPython with the embedded markers for SystemTap, the
SystemTap development tools must be installed.

On a Fedora or Red Hat Enterprise Linux machine, this can be done via::

   yum install systemtap-sdt-devel

CPython must then be configured `--with-systemtap`::

   checking for --with-systemtap... yes

You can verify if the SystemTap static markers are present in the built
binary by seeing if it contains a ".note.stapsdt" section.

.. code-block:: bash

   $ eu-readelf -S ./python | grep .note.stapsdt
   [29] .note.stapsdt        NOTE         0000000000000000 00308d78 000000b8  0        0   0  4

If you've built python as a shared library (with --enable-shared), you need
to look instead within the shared library.  For example:

.. code-block:: bash

   $ eu-readelf -S libpython3.3dm.so.1.0 | grep .note.stapsdt
   [28] .note.stapsdt        NOTE         0000000000000000 00365b68 000000b8  0        0   0  4

Earlier versions of SystemTap stored the markers in a ".probes" section.

For the curious, you can see the metadata for the static markers using this
invocation.

.. code-block:: bash

  $ eu-readelf -x .note.stapsdt ./python

  Hex dump of section [29] '.note.stapsdt', 184 bytes at offset 0x308d78:
    0x00000000 08000000 45000000 03000000 73746170 ....E.......stap
    0x00000010 73647400 d4664b00 00000000 4fc36600 sdt..fK.....O.f.
    0x00000020 00000000 488d9000 00000000 70797468 ....H.......pyth
    0x00000030 6f6e0066 756e6374 696f6e5f 5f656e74 on.function__ent
    0x00000040 72790038 40257261 78203840 25726478 ry.8@%rax 8@%rdx
    0x00000050 202d3440 25656378 00000000 08000000  -4@%ecx........
    0x00000060 46000000 03000000 73746170 73647400 F.......stapsdt.
    0x00000070 0d674b00 00000000 4fc36600 00000000 .gK.....O.f.....
    0x00000080 4a8d9000 00000000 70797468 6f6e0066 J.......python.f
    0x00000090 756e6374 696f6e5f 5f726574 75726e00 unction__return.
    0x000000a0 38402572 61782038 40257264 78202d34 8@%rax 8@%rdx -4
    0x000000b0 40256563 78000000                   @%ecx...

and a sufficiently modern eu-readelf can print the metadata:

.. code-block:: bash

  $ eu-readelf -n ./python

  Note section [ 1] '.note.gnu.build-id' of 36 bytes at offset 0x190:
    Owner          Data size  Type
    GNU                   20  GNU_BUILD_ID
      Build ID: a28f8db1b224530b0d38ad7b82a249cf7c3f18d6

  Note section [27] '.note.stapsdt' of 184 bytes at offset 0x1ae884:
    Owner          Data size  Type
    stapsdt               70  Version: 3
      PC: 0xe0d3a, Base: 0x14b150, Semaphore: 0x3ae882
      Provider: python, Name: function__return, Args: '8@%rbx 8@%r13 -4@%eax'
    stapsdt               69  Version: 3
      PC: 0xe0f37, Base: 0x14b150, Semaphore: 0x3ae880
      Provider: python, Name: function__entry, Args: '8@%rbx 8@%r13 -4@%eax'

The above metadata contains information for SystemTap describing how it can
patch strategically-placed machine code instructions to enable the tracing
hooks used by a SystemTap script.


Static markers
--------------

The low-level way to use the SystemTap integration is to use the static
markers directly.  This requires you to explicitly state the binary file
containing them.

For example, this script can be used to show the call/return hierarchy of a
Python script:

.. code-block:: c

   probe process('python').mark("function__entry") {
        filename = user_string($arg1);
        funcname = user_string($arg2);
        lineno = $arg3;

        printf("%s => %s in %s:%d\\n",
               thread_indent(1), funcname, filename, lineno);
   }

   probe process('python').mark("function__return") {
       filename = user_string($arg1);
       funcname = user_string($arg2);
       lineno = $arg3;

       printf("%s <= %s in %s:%d\\n",
              thread_indent(-1), funcname, filename, lineno);
   }

It can be invoked like this:

.. code-block:: bash

   $ stap \
     show-call-hierarchy.stp \
     -c ./python test.py

The output looks like this::

   11408 python(8274):        => __contains__ in Lib/_abcoll.py:362
   11414 python(8274):         => __getitem__ in Lib/os.py:425
   11418 python(8274):          => encode in Lib/os.py:490
   11424 python(8274):          <= encode in Lib/os.py:493
   11428 python(8274):         <= __getitem__ in Lib/os.py:426
   11433 python(8274):        <= __contains__ in Lib/_abcoll.py:366

where the columns are:

  - time in microseconds since start of script

  - name of executable

  - PID of process

and the remainder indicates the call/return hierarchy as the script executes.

For a `--enable-shared` build of CPython, the markers are contained within the
libpython shared library, and the probe's dotted path needs to reflect this. For
example, this line from the above example::

   probe process('python').mark("function__entry") {

should instead read::

   probe process('python').library("libpython3.3dm.so.1.0").mark("function__entry") {

(assuming a debug build of CPython 3.3)

.. I'm reusing the "c:function" type for markers

.. c:function:: function__entry(str filename, str funcname, int lineno)

   This marker indicates that execution of a Python function has begun.  It is
   only triggered for pure-python (bytecode) functions.

   The filename, function name, and line number are provided back to the
   tracing script as positional arguments, which must be accessed using
   `$arg1`, `$arg2`:

       * `$arg1` : `(const char *)` filename, accessible using `user_string($arg1)`

       * `$arg2` : `(const char *)` function name, accessible using
         `user_string($arg2)`

       * `$arg3` : `int` line number

       * `$arg4` : `(PyFrameObject *)`, the frame being executed

.. c:function:: function__return(str filename, str funcname, int lineno)

   This marker is the converse of `function__entry`, and indicates that
   execution of a Python function has ended (either via ``return``, or via an
   exception).  It is only triggered for pure-python (bytecode) functions.

   The arguments are the same as for `function__entry`


Tapsets
-------

The higher-level way to use the SystemTap integration is to use a "tapset":
SystemTap's equivalent of a library, which hides some of the lower-level
details of the static markers.

Here is a tapset file, based on a non-shared build of CPython:

.. code-block:: c

    /*
       Provide a higher-level wrapping around the function__entry and
       function__return markers:
     */
    probe python.function.entry = process("python").mark("function__entry")
    {
        filename = user_string($arg1);
        funcname = user_string($arg2);
        lineno = $arg3;
        frameptr = $arg4
    }
    probe python.function.return = process("python").mark("function__return")
    {
        filename = user_string($arg1);
        funcname = user_string($arg2);
        lineno = $arg3;
        frameptr = $arg4
    }

If this file is installed in SystemTap's tapset directory (e.g.
`/usr/share/systemtap/tapset`), then these additional probepoints become
available:

.. c:function:: python.function.entry(str filename, str funcname, int lineno, frameptr)

   This probe point indicates that execution of a Python function has begun.
   It is only triggered for pure-python (bytecode) functions.

.. c:function:: python.function.return(str filename, str funcname, int lineno, frameptr)

   This probe point is the converse of `python.function.return`, and indicates
   that execution of a Python function has ended (either via ``return``, or
   via an exception).  It is only triggered for pure-python (bytecode) functions.


Examples
--------
This SystemTap script uses the tapset above to more cleanly implement the
example given above of tracing the Python function-call hierarchy, without
needing to directly name the static markers:

.. code-block:: c

    probe python.function.entry
    {
      printf("%s => %s in %s:%d\n",
             thread_indent(1), funcname, filename, lineno);
    }

    probe python.function.return
    {
      printf("%s <= %s in %s:%d\n",
             thread_indent(-1), funcname, filename, lineno);
    }


The following script uses the tapset above to provide a top-like view of all
running CPython code, showing the top 20 most frequently-entered bytecode
frames, each second, across the whole system:

.. code-block:: c

    global fn_calls;

    probe python.function.entry
    {
      fn_calls[pid(), filename, funcname, lineno] += 1;
    }

    probe timer.ms(1000) {
        printf("\033[2J\033[1;1H") /* clear screen */
        printf("%6s %80s %6s %30s %6s\n",
               "PID", "FILENAME", "LINE", "FUNCTION", "CALLS")
        foreach ([pid, filename, funcname, lineno] in fn_calls- limit 20) {
            printf("%6d %80s %6d %30s %6d\n",
                pid, filename, lineno, funcname,
                fn_calls[pid, filename, funcname, lineno]);
        }
        delete fn_calls;
    }

