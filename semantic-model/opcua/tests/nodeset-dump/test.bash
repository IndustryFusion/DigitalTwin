
OPCUASERVER=opcua-server1.py
NODESETDUMP=../../nodeset-dump.py
NAMESPACE=http://examples.com/url1

function mydiff() {
    echo "$1"
    result="$2"
    expected="$3"
    echo "expected <=> result"
    diff ${expected} ${result} || exit 1
    echo Done
}


function startstop_opcua_server() {
    echo $1
    start=$2
    server_script=$3
    if [ "$start" = "true" ]; then
        (python3 ${server_script} &)
    else
        pkill -f ${server_script}
        sleep 1
    fi
    sleep 1
}


echo Start OPPCUA Server
echo -------------------
startstop_opcua_server "Stopping opcua server" false ${OPCUASERVER}
startstop_opcua_server "Starting context server" true ${OPCUASERVER}

echo Dump from OPUA Server
echo ---------------------
sleep 2
python3 ${NODESETDUMP} --namespaces ${NAMESPACE}

echo Compare Result
echo ---------------
mydiff "Compare nodeset2.xml" opcua-server1.nodeset2.xml nodeset2.xml
