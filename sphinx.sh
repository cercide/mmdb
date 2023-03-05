APPDIR=$(dirname $(readlink -f $0))

PROJECT_NAME=$(cat "${APPDIR}/pyproject.toml" | grep -Po "^name\s*=\s*['\"].+$" | sed "s/^name\s*=\s*['\"]//" | sed "s/['\"]\s*$//")
PROJECT_LICENSE=$(cat "${APPDIR}/pyproject.toml" | grep -Po "^license\s*=\s*['\"].+$" | sed "s/^license\s*=\s*['\"]//" | sed "s/['\"]\s*$//")
PROJECT_VERSION=$(cat "${APPDIR}/pyproject.toml" | grep -Po "^version\s*=\s*['\"].+$" | sed "s/^version\s*=\s*['\"]//" | sed "s/['\"]\s*$//")
PROJECT_AUTHOR=$(cat "${APPDIR}/pyproject.toml" | grep -Po "^authors\s*=\s*\[['\"].+$" | sed "s/^authors\s*=\s*\[//" | sed "s/\s*<[^>]*>//g" | sed "s/['\"]\s*,\s*/, /g" | sed "s/['\"\[\]]*//g")
PROJECT_RELEASE=$(date +%Y)

if ! [[ -d "$APPDIR/docs" ]]
then
  poetry run sphinx-quickstart \
    -p "$PROJECT_NAME" \
    -a "$PROJECT_AUTHOR" \
    -v "$PROJECT_VERSION" \
    -r "$PROJECT_RELEASE" \
    -l en \
    --sep \
    --extensions "sphinx.ext.napoleon,sphinx-pydantic,sphinx_rtd_theme,sphinx.ext.autosummary" \
    --ext-autodoc \
    --ext-doctest \
    --ext-todo \
    --ext-coverage \
    --ext-viewcode \
    "$APPDIR/docs"

    sed -e "/^# -- Project information/i import sys" -i "${APPDIR}/docs/source/conf.py"
    sed -e "/^# -- Project information/i from os.path import abspath" -i "${APPDIR}/docs/source/conf.py"
    sed -e "/^# -- Project information/i from os.path import dirname" -i "${APPDIR}/docs/source/conf.py"
    sed -e "/^# -- Project information/i from os.path import join" -i "${APPDIR}/docs/source/conf.py"
    sed -e "/^# -- Project information/i \ " -i "${APPDIR}/docs/source/conf.py"
    sed -e "/^# -- Project information/i appdir=abspath(join(dirname(abspath(__file__)), '..', '..'))" -i "${APPDIR}/docs/source/conf.py"
    sed -e "/^# -- Project information/i sys.path.insert(0, appdir)" -i "${APPDIR}/docs/source/conf.py"
    sed -e "/^# -- Project information/i \ " -i "${APPDIR}/docs/source/conf.py"

    sed -e "s/^html_theme.*$/html_theme = \"sphinx_rtd_theme\"/" -i "${APPDIR}/docs/source/conf.py"

    sed -e "s/^exclude_patterns.*$/exclude_patterns = ['.*\.bak', '.*\.tmp']/" -i "${APPDIR}/docs/source/conf.py"

    sed -e "s/:maxdepth: \d+/:maxdepth: 4/" -i "${APPDIR}/docs/source/index.rst"
fi

poetry run sphinx-apidoc -o $APPDIR/docs/source/apidoc $APPDIR

sed -e "/^\s*apidoc\/.*$/d" -i "${APPDIR}/docs/source/index.rst"
for fname in $(ls  $APPDIR/docs/source/apidoc)
do
    fname=${fname%.*}
    sed -e "/:caption: Contents:/a \ \ \ \ \ apidoc/${fname}" -i "${APPDIR}/docs/source/index.rst"
done

poetry run sphinx-build -b html $APPDIR/docs/source $APPDIR/docs/build
