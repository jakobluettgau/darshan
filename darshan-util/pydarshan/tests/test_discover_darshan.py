"""
Test the discover darshan discovery for the most important modes as far as CI
allows:
    
    LD_LIBRARY_PATH
        (this is explicitly set by the CI build)
        can probably disabled by purging the entry via fixture

    PATH/shutil.which
        this should fail at the moment, but can be achieved via fixture

    pkgconfig
        TODO: check if pkgconfig is available in the CI environemtn


    binary-wheel
        TODO: maybe automate wheel building first?

    pyinstaller
        TODO: requires binary wheel as well

""" 
