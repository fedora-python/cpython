provider python {
    probe function__entry(const char *, const char *, int, PyFrameObject *);
    probe function__return(const char *, const char *, int, PyFrameObject *);
};
