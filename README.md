# youtube_dl_playlist

__youtube_dl_playlist__ is a Python package designed to explain how to distribute packages via [PyPI]() (the Python Package Index) so they can be installed using `pip`.

__No se recomienda su uso para fines ajenos a los descritos arriba__.


## Installation
~~~sh
pip install youtube_dl_playlist
~~~

## Usage
Instantiate a sample and do amazing shit.
~~~py
from youtube_dl_playlist import Downloader
s = Downloader()
print(s.name())
~~~


## Tests
~~~sh
# from the project root
python -m unittest discover tests -v
~~~


## Contributing
If you want to improve __youtube_dl_playlist__, fork the repo and submit a pull request!

## License
This code is licensed under the [MIT License](https://opensource.org/licenses/MIT).



## How To

El mejor tutorial acerca de PyPI que he encontrado [está aquí](http://peterdowns.com/posts/first-time-with-pypi.html), este tutorial reproduce partes de su contenido.

La información oficial [está aquí](https://packaging.python.org/en/latest/distributing/).

First, create accounts with <https://pypi.python.org/> and <https://testpypi.python.org/pypi>. Then create your `~.pypirc` file.

`~/.pypirc`
~~~
[distutils]
index-servers =
  pypi
  pypitest

[pypi]
repository=https://pypi.python.org/pypi
username=<username>
password=<password>

[pypitest]
repository=https://testpypi.python.org/pypi
username=<username>
password=<password>
~~~


Tag your release and upload it to GitHub.
~~~sh
# add a tag to a package so that package can be submitted to PyPI
git tag <version> -m "Adds a versioning tag so that we can submit this to PyPI."

git push --tags origin master
# file is now available for download here
# https://github.com/<user>/<repo>/tarball/<tag>
~~~

Submit your package to __pypitest__ first. Check that it works, then submit it to __pypi__.
~~~sh
# submit to pypi test server
python setup.py register -r pypitest # register your package with PyPI
python setup.py sdist upload -r pypitest # push a new version to PyPI
pip install -i https://testpypi.python.org/pypi <package>

# submit to pypi
python setup.py register -r pypi
python setup.py sdist upload -r pypi
pip install <package>
~~~

