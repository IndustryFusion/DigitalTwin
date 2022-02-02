FROM python:3.8
RUN pip install kubernetes kopf==1.32.1 oisp pycodestyle pylint coverage aiounittest
ADD test/requirements.txt /opt/test/
RUN cd /opt/test && pip install -r requirements.txt
ADD *.py /opt/
ADD test/*.py /opt/test/
RUN PYTHONPATH=/opt python3 -m pycodestyle /opt/*.py
RUN PYTHONPATH=/opt python3 -m pylint --disable=fixme /opt/*.py
RUN PYTHONPATH=/opt coverage run /opt/test/test_beamservicesoperator.py && \ 
PYTHONPATH=/opt coverage run -a  /opt/test/test_tables_and_views.py && \
PYTHONPATH=/opt coverage run -a  /opt/test/test_util.py && \
PYTHONPATH=/opt coverage run -a  /opt/test/test_beamsqlstatementsetoperator.py && \
PYTHONPATH=/opt coverage run -a  /opt/test/test_flink_util.py && \
PYTHONPATH=/opt coverage run -a  /opt/test/test_util.py
RUN coverage report --omit "*/test*" -m --fail-under 80

FROM python:3.8
RUN pip install kubernetes kopf==1.32.1 oisp
ADD *.py /opt/
WORKDIR /opt
RUN groupadd -r bsoperator && useradd -r -g bsoperator bsoperator

USER bsoperator

CMD kopf run -A --standalone /opt/beamsqlstatementsetoperator.py