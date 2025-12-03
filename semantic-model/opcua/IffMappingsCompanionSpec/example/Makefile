#
# Copyright (c) 2025 Intel Corporation
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

ifdef DEBUG
DEBUG_FLAG := --debug
else
DEBUG_FLAG :=
endif
# -----------------------------------------------------------------------------
# Version and source NodeSet URLs
# -----------------------------------------------------------------------------
NODESET_VERSION := UA-1.05.03-2023-12-15
NODESET2OWL = ../../../opcua/nodeset2owl.py
EXTRACTTYPE = ../../../opcua/extractType.py
EXTRACTIFFBINDINGS = ../../../opcua/extractIffBindings.py

INSTANCE_TYPE           := http://mycompany.com/UA/ProprietaryModel/ProprietaryDataObjectType
INSTANCE_NS_PREFIX      := http://demo.machine/



CORE_NODESET              := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/Schema/Opc.Ua.NodeSet2.xml
CORE_SERVICES_NODESET     := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/Schema/Opc.Ua.NodeSet2.Services.xml
DI_NODESET                := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/DI/Opc.Ua.Di.NodeSet2.xml
PADIM_NODESET             := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/PADIM/Opc.Ua.PADIM.NodeSet2.xml
DICTIONARY_IRDI           := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/PADIM/Opc.Ua.IRDI.NodeSet2.xml
IA_NODESET                := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/IA/Opc.Ua.IA.NodeSet2.xml
MACHINERY_NODESET         := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/Machinery/Opc.Ua.Machinery.NodeSet2.xml
MACHINERY_PROCESSVALUES_NODESET := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/Machinery/ProcessValues/opc.ua.machinery.processvalues.xml
MACHINERY_JOBS_NODESET    := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/ISA95-JOBCONTROL/opc.ua.isa95-jobcontrol.nodeset2.xml
MACHINERY_RESULT_NODESET    :=  https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/Machinery/Result/Opc.Ua.Machinery.Result.NodeSet2.xml
LASERSYSTEMS_NODESET      := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/LaserSystems/Opc.Ua.LaserSystems.NodeSet2.xml
MACHINERY_EXAMPLE_NODESET := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/Machinery/Opc.Ua.Machinery.Examples.NodeSet2.xml
MACHINETOOL_NODESET       := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/MachineTool/Opc.Ua.MachineTool.NodeSet2.xml
PUMPS_NODESET             := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/Pumps/Opc.Ua.Pumps.NodeSet2.xml
PUMP_EXAMPLE_NODESET      := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/Pumps/instanceexample.xml
MACHINETOOL_EXAMPLE_NODESET := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/MachineTool/Machinetool-Example.xml
LASERSYSTEMS_EXAMPLE_NODESET := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/LaserSystems/LaserSystem-Example.NodeSet2.xml
PACKML_NODESET            := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/PackML/Opc.Ua.PackML.NodeSet2.xml

# -----------------------------------------------------------------------------
# Base Ontology URL and Remote Mode
# -----------------------------------------------------------------------------
BASE_ONTOLOGY := https://industryfusion.github.io/contexts/staging/ontology/v0/base.ttl

# When REMOTE is defined the dependencies (ontologies) come from remote URLs.
ifdef REMOTE
  OPCUA_PREFIX := https://industryfusion.github.io/contexts/staging/opcua/v0/
  $(info *** Remote mode selected ***)
else
  OPCUA_PREFIX :=
endif

# -----------------------------------------------------------------------------
# Target-specific variables
# For each target (for example “core”) we define:
#   CORE_NODESET_URL      – the NodeSet XML source URL
#   CORE_ONTOLOGY         – the output file name (also the target name)
#   CORE_DEPENDENCIES     – the list of files to pass to -i
#   CORE_OPTS             – extra options (such as -v and -p flags)
# -----------------------------------------------------------------------------

# CORE target
CORE_NODESET_URL      = $(CORE_NODESET)
CORE_ONTOLOGY         = core.ttl
CORE_DEPENDENCIES     = $(BASE_ONTOLOGY)
CORE_OPTS             = -v http://example.com/v0.1/UA/ -p opcua

# DEVICES target
DEVICES_NODESET_URL   = $(DI_NODESET)
DEVICES_ONTOLOGY      = devices.ttl
DEVICES_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
DEVICES_OPTS          = -v http://example.com/v0.1/DI/ -p devices

# IA target (Industrial Automation)
IA_NODESET_URL        = $(IA_NODESET)
IA_ONTOLOGY           = ia.ttl
IA_DEPENDENCIES       = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DEVICES_ONTOLOGY)
IA_OPTS               = -v http://example.com/v0.1/IA/ -p ia

# MACHINERY target
MACHINERY_NODESET_URL = $(MACHINERY_NODESET)
MACHINERY_ONTOLOGY    = machinery.ttl
MACHINERY_DEPENDENCIES = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DEVICES_ONTOLOGY)
MACHINERY_OPTS        = -v http://example.com/v0.1/Machinery/ -p machinery

# PUMPS target
PUMPS_NODESET_URL     = $(PUMPS_NODESET)
PUMPS_ONTOLOGY        = pumps.ttl
PUMPS_DEPENDENCIES    = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DEVICES_ONTOLOGY) $(MACHINERY_ONTOLOGY)
PUMPS_OPTS            = -v http://example.com/v0.1/Pumps/ -p pumps

# PUMPEXAMPLE target
PUMPEXAMPLE_NODESET_URL  = $(PUMP_EXAMPLE_NODESET)
PUMPEXAMPLE_ONTOLOGY     = pumpexample.ttl
PUMPEXAMPLE_DEPENDENCIES = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DEVICES_ONTOLOGY) $(MACHINERY_ONTOLOGY) $(PUMPS_ONTOLOGY)
PUMPEXAMPLE_OPTS         = -n http://yourorganisation.org/InstanceExample/ -v http://example.com/v0.1/pumpexample/ -p pumpexample

# MACHINETOOL target
MACHINETOOL_NODESET_URL   = $(MACHINETOOL_NODESET)
MACHINETOOL_ONTOLOGY      = machinetool.ttl
MACHINETOOL_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DEVICES_ONTOLOGY) $(MACHINERY_ONTOLOGY) $(IA_ONTOLOGY)
MACHINETOOL_OPTS          = -v http://example.com/v0.1/MachineTool/ -p machinetool

# LASERSYSTEMS target
LASERSYSTEMS_NODESET_URL   = $(LASERSYSTEMS_NODESET)
LASERSYSTEMS_ONTOLOGY      = lasersystems.ttl
LASERSYSTEMS_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DEVICES_ONTOLOGY) $(MACHINERY_ONTOLOGY) $(IA_ONTOLOGY) $(MACHINETOOL_ONTOLOGY)
LASERSYSTEMS_OPTS          = -v http://example.com/v0.1/LaserSystems/ -p lasersystems

# LASERSYSTEMSEXAMPLE target
LASERSYSTEMSEXAMPLE_NODESET_URL   = $(LASERSYSTEMS_EXAMPLE_NODESET)
LASERSYSTEMSEXAMPLE_ONTOLOGY      = lasersystemsexample.ttl
LASERSYSTEMSEXAMPLE_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DEVICES_ONTOLOGY) $(MACHINERY_ONTOLOGY) $(IA_ONTOLOGY) $(MACHINETOOL_ONTOLOGY) $(LASERSYSTEMS_ONTOLOGY)
LASERSYSTEMSEXAMPLE_OPTS          = -v http://example.com/v0.1/LaserSystems/ -p lasersystemsexample

# MACHINETOOLSEXAMPLE target
MACHINETOOLSEXAMPLE_NODESET_URL   = $(MACHINETOOL_EXAMPLE_NODESET)
MACHINETOOLSEXAMPLE_ONTOLOGY      = machinetoolexample.ttl
MACHINETOOLSEXAMPLE_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DEVICES_ONTOLOGY) $(MACHINERY_ONTOLOGY) $(MACHINETOOL_ONTOLOGY) $(IA_ONTOLOGY)
MACHINETOOLSEXAMPLE_OPTS          = -n http://yourorganisation.org/MachineTool-Example/ -v http://example.com/MachineToolExample/v0.1/pumpexample/ -p machinetoolexample

# MACHINERYEXAMPLE target
MACHINERYEXAMPLE_NODESET_URL   = $(MACHINERY_EXAMPLE_NODESET)
MACHINERYEXAMPLE_ONTOLOGY      = machineryexample.ttl
MACHINERYEXAMPLE_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DEVICES_ONTOLOGY) $(MACHINERY_ONTOLOGY)
MACHINERYEXAMPLE_OPTS          = -v http://example.com/MachineryExample/v0.1/pumpexample/ -p machineryexample

# DICTIONARY_IRDI target
DICTIONARY_IRDI_NODESET_URL   = $(DICTIONARY_IRDI)
DICTIONARY_IRDI_ONTOLOGY      = dictionary_irdi.ttl
DICTIONARY_IRDI_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
DICTIONARY_IRDI_OPTS          = -v http://example.com/v0.1/Dictionary/IRDI -p dictionary_irdi

# PADIM target
PADIM_NODESET_URL   = $(PADIM_NODESET)
PADIM_ONTOLOGY      = padim.ttl
PADIM_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DICTIONARY_IRDI_ONTOLOGY) $(DEVICES_ONTOLOGY)
PADIM_OPTS          = -v http://example.com/v0.1/PADIM -p padim

# MACHINERY_PROCESSVALUES target
MACHINERY_PROCESSVALUES_NODESET_URL   = $(MACHINERY_PROCESSVALUES_NODESET)
MACHINERY_PROCESSVALUES_ONTOLOGY      = machinery_processvalues.ttl
MACHINERY_PROCESSVALUES_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(PADIM_ONTOLOGY)
MACHINERY_PROCESSVALUES_OPTS          = -v http://example.com/v0.1/Machinery/ProcessValues -p machinery_processvalues

# MACHINERY_JOBS target
MACHINERY_JOBS_NODESET_URL   = $(MACHINERY_JOBS_NODESET)
MACHINERY_JOBS_ONTOLOGY      = machinery_jobs.ttl
MACHINERY_JOBS_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
MACHINERY_JOBS_OPTS          = -v http://example.com/v0.1/Machinery/Jobs -p machinery_jobs

# MACHINERY_RESULT target
MACHINERY_RESULT_NODESET_URL   = $(MACHINERY_RESULT_NODESET)
MACHINERY_RESULT_ONTOLOGY      = machinery_result.ttl
MACHINERY_RESULT_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
MACHINERY_RESULT_OPTS          = -v http://example.com/v0.1/Machinery/Result -p machinery_result

# PACKML target
PACKML_NODESET_URL   = $(PACKML_NODESET)
PACKML_ONTOLOGY      = packml.ttl
PACKML_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
PACKML_OPTS          = -p packml

# COMPANY-SPECIFICATION
COMPANY_PROPRIETARYMODEL_NODESET_URL	= company_proprietarymodel.nodeset2.xml
COMPANY_PROPRIETARYMODEL_ONTOLOGY 		= company_proprietarymodel.ttl
COMPANY_PROPRIETARYMODEL_DEPENDENCIES	= $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
COMPANY_PROPRIETARYMODEL_OPTS 			= -p company_proprietarymodel

# IFF-Mapping
IFFMAPPING_NODESET_URL	= iffmapping.nodeset2.xml
IFFMAPPING_ONTOLOGY		= iffmapping.ttl
IFFMAPPING_DEPENDENCIES	= $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(COMPANY_PROPRIETARYMODEL_ONTOLOGY)
IFFMAPPING_OPTS			= -p iffmapping

# Company-Bindings
COMPANY_IFFBINDINGS_NODESET_URL 	= company_iffbindings.nodeset2.xml
COMPANY_IFFBINDINGS_ONTOLOGY 		= company_iffbindings.ttl
COMPANY_IFFBINDINGS_DEPENDENCIES 	= $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(COMPANY_PROPRIETARYMODEL_ONTOLOGY) $(IFFMAPPING_ONTOLOGY)
COMPANY_IFFBINDINGS_OPTS 			= -p company_iffbindings

# -----------------------------------------------------------------------------
# List of all target files to be built.
# -----------------------------------------------------------------------------
TARGET_NAMES = CORE COMPANY_PROPRIETARYMODEL IFFMAPPING COMPANY_IFFBINDINGS

ALL_TARGETS = $(foreach t, $(TARGET_NAMES), $($(t)_ONTOLOGY))


.PHONY: all clean ontology instances iffbindings
ontology: $(ALL_TARGETS)
instances: ontology shacl.ttl 

all: ontology instances iffbindings

# -----------------------------------------------------------------------------
# Generic rule to build a .ttl file.
#
# The pattern rule works as follows:
#
#   For a target like “core.ttl” the stem “core” is converted to uppercase
#   (i.e. CORE) and then the variables
#
#       CORE_NODESET_URL, CORE_DEPENDENCIES, and CORE_OPTS
#
#   are used in the command line.
# -----------------------------------------------------------------------------
%.ttl: core.ttl
	@echo "Creating $@"
	$(eval NAME := $(shell echo $* | tr a-z A-Z))
	echo  $(NAME)_DEPENDENCIES
	python3 $(NODESET2OWL) $($(NAME)_NODESET_URL) -i $($(NAME)_DEPENDENCIES) $($(NAME)_OPTS) -o $@

# -----------------------------------------------------------------------------
# BUILD instance file
#
# -----------------------------------------------------------------------------
INSTANCE_ONTOLOGY = $(COMPANY_PROPRIETARYMODEL_ONTOLOGY)
shacl.ttl instances.jsonld entities.ttl context.jsonld: $(COMPANY_PROPRIETARYMODEL_ONTOLOGY) ontology
	echo "Creating shacl.ttl, instances.jsonld, context.jsonld and entities.ttl"
	python3 $(EXTRACTTYPE) -t $(INSTANCE_TYPE) -n $(INSTANCE_NS_PREFIX) $(INSTANCE_ONTOLOGY)

iffbindings: ontology
	@echo "Extracting IFF Bindings"
	python3 $(EXTRACTIFFBINDINGS) $(COMPANY_IFFBINDINGS_ONTOLOGY) $(DEBUG_FLAG)
# -----------------------------------------------------------------------------
# Inter-target dependencies (if you need to ensure that some ontologies are built
# before others, list them here)
# -----------------------------------------------------------------------------
# --- Automatically generate dependency rules ---
$(foreach t, $(TARGET_NAMES), \
  $(eval $($(t)_ONTOLOGY): $(filter-out $(BASE_ONTOLOGY), $($(t)_DEPENDENCIES))))

DEP_NAMES = COMPANY_PROPRIETARYMODEL IFFMAPPING COMPANY_IFFBINDINGS
$(foreach t, $(DEP_NAMES), \
  $(eval $($(t)_ONTOLOGY): $($(t)_NODESET_URL)))
# -----------------------------------------------------------------------------
# Clean target: remove all generated .ttl files.
# -----------------------------------------------------------------------------
clean:
	@echo "Cleaning generated files..."
	$(foreach t, $(TARGET_NAMES), \
		 rm -f $($(t)_ONTOLOGY))
	rm -f shacl.ttl instances.jsonld bindings.ttl entities.ttl
