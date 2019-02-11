from youtube_dl_playlist.command_line import main


if __name__ == '__main__':
    """Ensure that the script can be invoked from the command line while testing
    the package, i.e. without going through the shim created by `setuptools` when
    the package is installed.
    """
    main()
