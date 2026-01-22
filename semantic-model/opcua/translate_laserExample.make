#
# Copyright (c) 2026 Intel Corporation
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

# Makefile for generating TTL files from NodeSet XML files using nodeset2owl.py

# Version and source NodeSet URLs
INSTANCE_NS_PREFIX 	:= http://demo.machine/
ONTOLOGY_NS 		:= http://vdma.org/UA/LaserSystem-Example/
INSTANCE_TYPE 		:= http://opcfoundation.org/UA/LaserSystems/LaserSystemType

# Base Ontology URL
BASE_ONTOLOGY := https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl

# Set OPCUA_PREFIX based on whether remote mode is enabled.
# By default (local mode) the generated files are used (empty prefix).
ifdef REMOTE
  OPCUA_PREFIX := TBD
  $(info *** Remote mode selected ***)
else
  OPCUA_PREFIX :=
endif

# Makefile for generating TTL files from NodeSet XML files using nodeset2owl.py

# -----------------------------------------------------------------------------
# Version and source NodeSet URLs
# -----------------------------------------------------------------------------
NODESET_DIR := .

INSTANCE_NODESET          	:= https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/LaserSystems/LaserSystem-Example.NodeSet2.xml

# Dependent Ontology URLs (or local files if not in remote mode)
CORE_ONTOLOGY                       := $(OPCUA_PREFIX)core.ttl
DEVICES_ONTOLOGY                    := $(OPCUA_PREFIX)devices.ttl
MACHINERY_ONTOLOGY                  := $(OPCUA_PREFIX)machinery.ttl
MACHINERY_JOBS_ONTOLOGY             := $(OPCUA_PREFIX)machinery_jobs.ttl
MACHINERY_RESULT_ONTOLOGY             := $(OPCUA_PREFIX)machinery_result.ttl
MACHINERY_PROCESSVALUES_ONTOLOGY    := $(OPCUA_PREFIX)machinery_processvalues.ttl
PUMPS_ONTOLOGY                      := $(OPCUA_PREFIX)pumps.ttl
IA_ONTOLOGY                         := $(OPCUA_PREFIX)ia.ttl
MACHINETOOL_ONTOLOGY                := $(OPCUA_PREFIX)machinetool.ttl
LASERSYSTEMS_ONTOLOGY               := $(OPCUA_PREFIX)lasersystems.ttl
DICTIONARY_IRDI_ONTOLOGY            := $(OPCUA_PREFIX)dictionary_irdi.ttl
PADIM_ONTOLOGY                      := $(OPCUA_PREFIX)padim.ttl
PACKML_ONTOLOGY                     := $(OPCUA_PREFIX)packml.ttl


# Instance Definition and dependencies
INSTANCE_URL           			:= $(INSTANCE_NODESET)
INSTANCE_ONTOLOGY          		:= lasersystemsexample.ttl
INSTANCE_OPTS					:= -p lasersystemsexample -n $(ONTOLOGY_NS)
INSTANCE_JSONLD_OPTS			:= -n $(INSTANCE_IRI)
INSTANCE_TYPE					:= $(INSTANCE_TYPE)
INSTANCE_DEPENDENCIES      		= $(CORE_ONTOLOGY) $(DEVICES_ONTOLOGY) $(MACHINERY_ONTOLOGY) $(IA_ONTOLOGY) $(MACHINETOOL_ONTOLOGY) $(LASERSYSTEMS_ONTOLOGY)


# -----------------------------------------------------------------------------
# BUILD instance file
#
# -----------------------------------------------------------------------------
shacl.ttl instances.jsonld entities.ttl context.jsonld $(INSTANCE_ONTOLOGY): $(INSTANCE_DEPENDENCIES)
	@echo "Creating $@"
	python3 nodeset2owl.py  $(INSTANCE_URL) -i $(INSTANCE_DEPENDENCIES) $(INSTANCE_OPTS) -o $(INSTANCE_ONTOLOGY)
	echo "Creating shacl.ttl, instances.jsonld, context.jsonld and entities.ttl"
	python3 extractType.py -p -ma -i "sn1234" -sb -n $(INSTANCE_NS_PREFIX) $(INSTANCE_ONTOLOGY)


$(INSTANCE_DEPENDENCIES):
	@echo "Building missing default nodesets"
	make -f translate_default_nodesets.make $(INSTANCE_DEPENDENCIES)
# -----------------------------------------------------------------------------
# Inter-target dependencies (if you need to ensure that some ontologies are built
# before others, list them here)
# -----------------------------------------------------------------------------


all: $(INSTANCE)

# Clean target to remove generated TTL files
clean:
	@echo "Cleaning generated files..."
	rm -f  $(INSTANCE) shacl.ttl instances.jsonld entities.ttl context.jsonld
