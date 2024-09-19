#! /bin/bash

#Install miniconda with python 3.10 version
mkdir -p ./miniconda3
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ./miniconda3/miniconda.sh
bash ./miniconda3/miniconda.sh -b -u -p ./miniconda3
source ./miniconda3/bin/conda init
rm ./miniconda3/miniconda.sh