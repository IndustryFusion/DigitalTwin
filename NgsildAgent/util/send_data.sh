#!/bin/bash
# Copyright (c) 2023 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
set +e

# shellcheck disable=SC1091
. ./common.sh

usage="Usage: $(basename "$0") [-a] [-t] [-y <attribute type>] [-d datasetId] [<propertyname> <value>]+ \n\
-a: send array of values\n\
-t: use tcp connection to agent (default: udp)\n\
-d: give ngsild datasetId (must be iri)\n\
-y: attribute types are {Literal, Iri, Relationship, Json}\n"
while getopts 'athy:d:' opt; do
  # shellcheck disable=SC2221,SC2222
  case "$opt" in
    a)
      array=true
      ;;
    t)
      tcp=true
      ;;
    y)
      arg="$OPTARG"
      attribute_type=$arg
      ;;
    d)
      arg="$OPTARG"
      datasetId=$arg
     ;;
    ?|h)
      printf "$usage"
      exit 1
      ;;
  esac
done
shift "$((OPTIND -1))"

if [ -z "$attribute_type" ]; then
  attribute_type=Property
else
  case "$attribute_type" in
    Literal)
      attribute_type=PropertyLiteral
      ;;
    Iri)
      attribute_type=PropertyIri
      ;;
    Json)
      attribute_type=PropertyJson
      ;;
    Relationship)
      attribute_type=Relationship
      ;;
    *)
      echo "Wrong Attribute given: ${attribute_type}. Not sending data."
      exit 1
      ;;
  esac
fi

num_args=$#
if [ "${num_args}" -eq 2 ] && [ -z "$array" ]; then
  propName="$1"
  value="$2"
  payload='{"n":"'${propName}'", "v":"'${value}'", "t":"'$attribute_type'"'
  if [ -n "$datasetId" ]; then
    payload=${payload}', "d":"'$datasetId'"'
  fi
  payload=${payload}'}'
  echo $payload
elif [ "$((num_args%2))" -eq 0 ] && [ -n "$array" ]; then
  payload="["
  while [ "$#" -gt 0 ]; do
    payload="${payload}{\"n\": \"$1\", \"v\": \"$2\", \"t\":\"$attribute_type\""
    if [ -n "$datasetId" ]; then
      payload=${payload}', "d":"'$datasetId'"'
    fi
    payload=${payload}'}'
    shift 2
    if [ $# -gt 0 ]; then
      payload="${payload},"
    fi
  done
  payload="${payload}]"
elif [ -z "$array" ]; then
  echo "Error: Expected propertyname and value"
  printf "${usage}"
  exit 1
else
  echo "Error: Expected even number of arguments to form propertyname and value pairs."
  printf "${usage}"
  exit 1
fi

if [ -z "$CONFIG_FILE" ]; then
  echo "$CONFIG_FILE does not exists. Please prepare it!"
  exit 1
fi
if [ -z "$tcp" ]; then
  udpPort=$(jq '.listeners.udp_port' "$CONFIG_FILE")

  if [ -z "$udpPort" ]; then
    echo "No UDP Port found. Please check $CONFIG_FILE"
  fi

  echo "sending $payload to local UDP port ${udpPort}"
  echo -n "$payload"  > /dev/udp/127.0.0.1/"${udpPort}"
else
  tcpPort=$(jq '.listeners.tcp_port' "$CONFIG_FILE")

  if [ -z "$tcpPort" ]; then
    echo "No TCP Port found. Please check $CONFIG_FILE"
  fi

  echo "sending $payload to local TCP port ${tcpPort}"
  echo -n "$payload"  > /dev/tcp/127.0.0.1/"${tcpPort}"
fi