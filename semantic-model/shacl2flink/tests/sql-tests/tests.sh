#!/bin/bash
OUTPUTDIR=output
TOOLDIR=$(cd ../..; echo $PWD)
KMS=kms
TESTOUT=testout
SHACLOUT=shaclout
RESULT=result
testdirs=${@:-"$(ls $KMS)"}


for testdir in ${testdirs}; do
    KNOWLEDGE=knowledge.ttl
    SHACL=shacl.ttl
    pushd .
    cd $KMS/$testdir
    mkdir -p $OUTPUTDIR

    python3 $TOOLDIR/create_rdf_table.py ${KNOWLEDGE}
    python3 $TOOLDIR/create_core_tables.py
    python3 $TOOLDIR/create_sql_checks_from_shacl.py ${SHACL} ${KNOWLEDGE}

    for model in $(ls model*.jsonld); do
        MODEL=$model
        DATABASE=$OUTPUTDIR/database.db
        rm -f ${DATABASE}
        echo -n "Test with model ${MODEL} in dir ${testdir} ..."
        python3 $TOOLDIR/create_ngsild_models.py  ${SHACL} ${KNOWLEDGE} ${MODEL}
        python3 $TOOLDIR/create_ngsild_tables.py ${SHACL}
        # Test logic
        sqlite3 ${DATABASE} < $OUTPUTDIR/rdf.sqlite
        sqlite3 ${DATABASE} < $OUTPUTDIR/core.sqlite
        sqlite3 ${DATABASE} < $OUTPUTDIR/ngsild.sqlite
        sqlite3 ${DATABASE} < $OUTPUTDIR/ngsild-models.sqlite
        sqlite3 ${DATABASE} < $OUTPUTDIR/shacl-validation.sqlite
        echo "select resource, event, severity from alerts_bulk_view;" | sqlite3 -quote  -noheader ${DATABASE}| sort > ${OUTPUTDIR}/${MODEL}_${TESTOUT}
        diff ${OUTPUTDIR}/${MODEL}_${TESTOUT} ${MODEL}_${RESULT} || { echo "failed"; exit 1; }
        # Compare it with pyshacl results
        # pyshacl -s ${SHACL} -df json-ld ${MODEL} -e ${KNOWLEDGE} > ${OUTPUTDIR}/${MODEL}_${SHACLOUT} # disabled due to CWE-918 Reported by Snyk
        echo " ok"
    done;
    [ "$DEBUG" = "true" ] || rm -rf $OUTPUTDIR
    popd
done;