
> **Warning**
> In development. There is no usage yet, please be more patient for now.

# Librarian app

Librarian - simple documentation generator based on searching for `README.md`
files and doxygen syntax. Librarian provides two options: building raw html
documentation and providing small web-server documentation that allows
modifications with cli runtime.

## Configuration

You have different ways of config:

* Through tox file
* Through Command Line

### TOX file

Tox file is just running the command line options but from the command line, so
there is no additional steps todo.

### Command line

Command line provides options to configure all aspects of runtime. Most of them
are shown trough the `--help` option of each command. For the full list just
read the docs or run `librarian help --options` to get help for all options
that might be used.

There is option for man page documentation for the librarian. This available with
default installation.
