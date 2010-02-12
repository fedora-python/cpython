/*
  Support for SystemTap static markers  
*/

#ifdef WITH_SYSTEMTAP

#include "pysystemtap.h"

/*
  A struct to hold all of the information gathered when one of the traceable
  markers is triggered
*/
struct frame_marker_info
{
    PyObject *filename_obj;
    PyObject *funcname_obj;
    const char *filename;
    const char *funcname;
    int lineno;
};

static void
get_frame_marker_info(PyFrameObject *f, struct frame_marker_info *fmi)
{
    PyObject *ptype;
    PyObject *pvalue;
    PyObject *ptraceback;

    PyErr_Fetch(&ptype, &pvalue, &ptraceback);

    fmi->filename_obj = PyUnicode_EncodeFSDefault(f->f_code->co_filename);
    if (fmi->filename_obj) {
        fmi->filename = PyBytes_AsString(fmi->filename_obj);
    } else {
        fmi->filename = NULL;
    }

    fmi->funcname_obj = PyUnicode_AsUTF8String(f->f_code->co_name);
    if (fmi->funcname_obj) {
        fmi->funcname = PyBytes_AsString(fmi->funcname_obj);
    } else {
        fmi->funcname = NULL;
    }

    fmi->lineno = PyCode_Addr2Line(f->f_code, f->f_lasti);

    PyErr_Restore(ptype, pvalue, ptraceback);

}

static void
release_frame_marker_info(struct frame_marker_info *fmi)
{
    Py_XDECREF(fmi->filename_obj);
    Py_XDECREF(fmi->funcname_obj);
}

static void
systemtap_function_entry(PyFrameObject *f)
{
    struct frame_marker_info fmi;
    get_frame_marker_info(f, &fmi);
    PYTHON_FUNCTION_ENTRY(fmi.filename, fmi.funcname, fmi.lineno, f);
    release_frame_marker_info(&fmi);
}

static void
systemtap_function_return(PyFrameObject *f)
{
    struct frame_marker_info fmi;
    get_frame_marker_info(f, &fmi);
    PYTHON_FUNCTION_RETURN(fmi.filename, fmi.funcname, fmi.lineno, f);
    release_frame_marker_info(&fmi);
}

#else /* #ifdef WITH_SYSTEMTAP */

/*
  When configured --without-systemtap, everything compiles away to nothing:
*/
#define PYTHON_FUNCTION_ENTRY_ENABLED() 0
#define PYTHON_FUNCTION_RETURN_ENABLED() 0
#define systemtap_function_entry(f)
#define systemtap_function_return(f)

#endif
