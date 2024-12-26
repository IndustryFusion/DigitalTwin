#!/bin/bash
OUTPUTDIR=output
TOOLDIR=$(cd ../..; echo $PWD)
KMS_CONSTRAINTS=kms-constraints
KMS_RULES=kms-rules
KMS_UDF=kms-udf
TESTOUT=testout
SHACLOUT=shaclout
RESULT=result
testdirs_constraints=${@:-"$(ls ${KMS_CONSTRAINTS})"}
testdirs_rules=${@:-"$(ls ${KMS_RULES})"}
testdirs_udf=${@:-"$(ls ${KMS_UDF})"}
for testdir in ${testdirs_constraints}; do
    echo Entering test ${testdir} in  ${KMS_CONSTRAINTS}
    KNOWLEDGE=knowledge.ttl
    SHACL=shacl.ttl
    CONTEXT=context.jsonld
    pushd .
    cd $KMS_CONSTRAINTS/$testdir || break
    mkdir -p $OUTPUTDIR

    python3 $TOOLDIR/create_rdf_table.py ${KNOWLEDGE}
    python3 $TOOLDIR/create_core_tables.py
    python3 $TOOLDIR/create_sql_checks_from_shacl.py -c ${CONTEXT} ${SHACL} ${KNOWLEDGE} 

    for model in $(ls model*.jsonld); do
        MODEL=$model
        DATABASE=$OUTPUTDIR/database.db
        rm -f ${DATABASE}
        echo -n "Test with model ${MODEL} in dir ${testdir} ..."
        python3 $TOOLDIR/create_ngsild_models.py  ${SHACL} ${KNOWLEDGE} ${MODEL}
        python3 $TOOLDIR/create_ngsild_tables.py
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

for testdir in ${testdirs_rules}; do
    echo Entering test ${testdir} in ${KMS_RULES}
    KNOWLEDGE=knowledge.ttl
    SHACL=shacl.ttl
    pushd .
    cd $KMS_RULES/$testdir || break
    mkdir -p $OUTPUTDIR

    python3 $TOOLDIR/create_rdf_table.py ${KNOWLEDGE}
    python3 $TOOLDIR/create_core_tables.py
    python3 $TOOLDIR/create_sql_checks_from_shacl.py  -c ${CONTEXT} ${SHACL} ${KNOWLEDGE}

    for model in $(ls model*.jsonld); do
        MODEL=$model
        DATABASE=$OUTPUTDIR/database.db
        rm -f ${DATABASE}
        echo -n "Test with model ${MODEL} in dir ${testdir} ..."
        python3 $TOOLDIR/create_ngsild_models.py  ${SHACL} ${KNOWLEDGE} ${MODEL}
        python3 $TOOLDIR/create_ngsild_tables.py 
        # Test logic
        sqlite3 ${DATABASE} < $OUTPUTDIR/rdf.sqlite
        sqlite3 ${DATABASE} < $OUTPUTDIR/core.sqlite
        sqlite3 ${DATABASE} < $OUTPUTDIR/ngsild.sqlite
        sqlite3 ${DATABASE} < $OUTPUTDIR/ngsild-models.sqlite
        sqlite3 ${DATABASE} < $OUTPUTDIR/shacl-validation.sqlite
        echo "select entityId, name, nodeType, valueType, datasetId, \`type\`, attributeValue from attributes_insert_filter;" | sqlite3 -quote  -noheader ${DATABASE} | LC_ALL="en_US.UTF-8" sort > ${OUTPUTDIR}/${MODEL}_${TESTOUT}
        diff ${OUTPUTDIR}/${MODEL}_${TESTOUT} ${MODEL}_${RESULT} || { echo "failed"; exit 1; }
        echo " ok"
    done;
    [ "$DEBUG" = "true" ] || rm -rf $OUTPUTDIR
    popd
done;

for testdir in ${testdirs_udf}; do
    echo Entering test ${testdir} in ${KMS_UDF}
    KNOWLEDGE=knowledge.ttl
    SHACL=shacl.ttl
    pushd .
    cd $KMS_UDF/$testdir
    mkdir -p $OUTPUTDIR

    python3 $TOOLDIR/create_rdf_table.py ${KNOWLEDGE}
    python3 $TOOLDIR/create_core_tables.py
    python3 $TOOLDIR/create_sql_checks_from_shacl.py -c ${CONTEXT} ${SHACL} ${KNOWLEDGE}

    for model in $(ls model*.jsonld); do
        MODEL=$model
        DATABASE=$OUTPUTDIR/database.db
        rm -f ${DATABASE}
        echo -n "Test with model ${MODEL} in dir ${testdir} ..."
        python3 $TOOLDIR/create_ngsild_models.py  ${SHACL} ${KNOWLEDGE} ${MODEL}
        python3 $TOOLDIR/create_ngsild_tables.py
        # Test logic
        sqlite3 ${DATABASE} < $OUTPUTDIR/rdf.sqlite
        sqlite3 ${DATABASE} < $OUTPUTDIR/core.sqlite
        sqlite3 ${DATABASE} < $OUTPUTDIR/ngsild.sqlite
        sqlite3 ${DATABASE} < $OUTPUTDIR/ngsild-models.sqlite
        #sqlite3 ${DATABASE} < $OUTPUTDIR/shacl-validation.sqlite
        python3 ${TOOLDIR}/udf/sqlite3_insert.py ${DATABASE} ${OUTPUTDIR}/shacl-validation.sqlite
        echo "select entityId, name, nodeType, valueType, datasetId, \`type\`, attributeValue from attributes_insert_filter;" | sqlite3 -quote  -noheader ${DATABASE} | LC_ALL="en_US.UTF-8" sort > ${OUTPUTDIR}/${MODEL}_${TESTOUT}
        diff ${OUTPUTDIR}/${MODEL}_${TESTOUT} ${MODEL}_${RESULT} || { echo "failed"; exit 1; }
        echo " ok"
    done;
    [ "$DEBUG" = "true" ] || rm -rf $OUTPUTDIR
    popd
done;
