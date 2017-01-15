#!/usr/bin/env bash
set -x

# The build script for https://github.com/weibeld/heroku-buildpack-run


STORAGE_LOCN=$(pwd)

# ----------

mkdir -p "$1" "$2" "$3"
build=$(cd "$1/" && pwd)
cache=$(cd "$2/" && pwd)
env_dir=$(cd "$3/" && pwd)

# -------

wget -q https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
bash miniconda.sh -b -p $HOME/.conda
$HOME/.conda/bin/conda install --yes -c defaults -c conda-forge \
         gitpython pygithub jinja2 tornado requests pandas nomkl pip dask
$HOME/.conda/bin/pip install -r requirements.txt

# We want the new get_stargazers_with_dates (https://github.com/PyGithub/PyGithub/pull/347) which isn't in a release yet.
$HOME/.conda/bin/pip install https://github.com/PyGithub/PyGithub --upgrade

cp -rf $HOME/.conda $STORAGE_LOCN/.conda

$HOME/.conda/bin/conda clean --all --yes

mkdir -p $build/.profile.d
cat <<-'EOF' > $build/.profile.d/conda.sh
    # append to path variable
    export PATH=$HOME/.conda/bin:$PATH

EOF
