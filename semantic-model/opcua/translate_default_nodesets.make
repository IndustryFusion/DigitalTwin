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

# -----------------------------------------------------------------------------
# Version and source NodeSet URLs
# -----------------------------------------------------------------------------
NODESET_VERSION := UA-1.05.03-2023-12-15
DSB :=
ifneq ($(DISABLE_SEMANTIC_BRIDGE), )
	DSB := --disable-semantic-bridge
endif


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
TMC_NODESET               := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/TMC/Opc.Ua.TMC.NodeSet2.xml
DEXPI_NODESET             := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/DEXPI/Opc.Ua.DEXPI.NodeSet2.xml
ISA95_NODESET             := https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/$(NODESET_VERSION)/ISA-95/Opc.ISA95.NodeSet2.xml

# Server URI (svu) of the example instance nodesets. Instance nodes are dynamic, i.e. server
# specific, and are only exported by nodeset2owl.py when a server URI is given.
SERVER_URI ?= urn:example:opcua-server
# Second server of the compose2 example (two servers with the same NodeIds in one knowledge graph).
SERVER_URI2 ?= urn:example:opcua-server2

# -----------------------------------------------------------------------------
# Base Ontology URL and Remote Mode
# -----------------------------------------------------------------------------
# BASE_ONTOLOGY is the fetchable *document* (passed to -i/-burl): the v0.3
# document is a patched version of the base ontology (fixing inconsistencies
# such as isAbstract boolean/string mismatches and overly-strict datatype
# property ranges), but it still declares its own terms under the original,
# unchanged v0 namespace -- verified directly against the hosted document,
# which itself declares `@prefix base: <.../ontology/v0/base/> .`. So
# BASE_ONTOLOGY_NS (passed to -b, the *term namespace* used to mint every
# base:xxx IRI throughout the pipeline) must stay at v0/base/, NOT be bumped
# to the v0.3 document URL: -b and -burl are a different kind of thing (a
# namespace vs. a document location) and must not be conflated. Doing so
# previously caused two bugs: (1) owl:imports rendering as a bare "base:"
# token instead of a visible IRI, since Turtle collapses a URIRef that
# exactly equals a bound namespace's value into a prefix-only token; (2) far
# more seriously, every generated base:xxx term becoming a malformed,
# separator-less run-on IRI (e.g. ".../base.ttlSemanticBridgeReferenceType"
# instead of ".../base/SemanticBridgeReferenceType"), silently disconnecting
# every base:* reference in the whole corpus from the real base ontology's
# own term definitions.
BASE_ONTOLOGY_NS := https://industryfusion.github.io/contexts/ontology/v0/base/
BASE_ONTOLOGY := https://industryfusion.github.io/contexts/staging/ontology/v0.3/base.ttl

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
CORE_ONTOLOGY         = core.owl.ttl
CORE_OWL              = core.vt.owl.ttl
CORE_DEPENDENCIES     = $(BASE_ONTOLOGY)
CORE_OPTS             = -v http://example.com/v0.1/UA/ -p opcua

# DI target
DI_NODESET_URL   = $(DI_NODESET)
DI_ONTOLOGY      = di.owl.ttl
DI_OWL           = di.vt.owl.ttl
DI_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
DI_OPTS          = -v http://example.com/v0.1/DI/ -p di

# IA target (Industrial Automation)
IA_NODESET_URL        = $(IA_NODESET)
IA_ONTOLOGY           = ia.owl.ttl
IA_OWL                = ia.vt.owl.ttl
IA_DEPENDENCIES       = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DI_ONTOLOGY)
IA_OPTS               = -v http://example.com/v0.1/IA/ -p ia

# MACHINERY target
MACHINERY_NODESET_URL = $(MACHINERY_NODESET)
MACHINERY_ONTOLOGY    = machinery.owl.ttl
MACHINERY_OWL         = machinery.vt.owl.ttl
MACHINERY_DEPENDENCIES = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DI_ONTOLOGY)
MACHINERY_OPTS        = -v http://example.com/v0.1/Machinery/ -p machinery

# PUMPS target
PUMPS_NODESET_URL     = $(PUMPS_NODESET)
PUMPS_ONTOLOGY        = pumps.owl.ttl
PUMPS_OWL             = pumps.vt.owl.ttl
PUMPS_DEPENDENCIES    = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DI_ONTOLOGY) $(MACHINERY_ONTOLOGY)
PUMPS_OPTS            = -v http://example.com/v0.1/Pumps/ -p pumps

# PUMPEXAMPLE target
PUMPEXAMPLE_NODESET_URL  = $(PUMP_EXAMPLE_NODESET)
PUMPEXAMPLE_ONTOLOGY     = pumpexample.owl.ttl
PUMPEXAMPLE_OWL          = pumpexample.vt.owl.ttl
PUMPEXAMPLE_DEPENDENCIES = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DI_ONTOLOGY) $(MACHINERY_ONTOLOGY) $(PUMPS_ONTOLOGY)
PUMPEXAMPLE_OPTS         = -n http://yourorganisation.org/InstanceExample/ -v http://example.com/v0.1/pumpexample/ -p pumpexample --serverUri $(SERVER_URI)

# MACHINETOOL target
MACHINETOOL_NODESET_URL   = $(MACHINETOOL_NODESET)
MACHINETOOL_ONTOLOGY      = machinetool.owl.ttl
MACHINETOOL_OWL           = machinetool.vt.owl.ttl
MACHINETOOL_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DI_ONTOLOGY) $(MACHINERY_ONTOLOGY) $(IA_ONTOLOGY)
MACHINETOOL_OPTS          = -v http://example.com/v0.1/MachineTool/ -p machinetool

# LASERSYSTEMS target
LASERSYSTEMS_NODESET_URL   = $(LASERSYSTEMS_NODESET)
LASERSYSTEMS_ONTOLOGY      = lasersystems.owl.ttl
LASERSYSTEMS_OWL           = lasersystems.vt.owl.ttl
LASERSYSTEMS_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DI_ONTOLOGY) $(MACHINERY_ONTOLOGY) $(IA_ONTOLOGY) $(MACHINETOOL_ONTOLOGY)
LASERSYSTEMS_OPTS          = -v http://example.com/v0.1/LaserSystems/ -p lasersystems

# LASERSYSTEMSEXAMPLE target
LASERSYSTEMSEXAMPLE_NODESET_URL   = $(LASERSYSTEMS_EXAMPLE_NODESET)
LASERSYSTEMSEXAMPLE_ONTOLOGY      = lasersystemsexample.owl.ttl
LASERSYSTEMSEXAMPLE_OWL           = lasersystemsexample.vt.owl.ttl
LASERSYSTEMSEXAMPLE_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DI_ONTOLOGY) $(MACHINERY_ONTOLOGY) $(IA_ONTOLOGY) $(MACHINETOOL_ONTOLOGY) $(LASERSYSTEMS_ONTOLOGY)
LASERSYSTEMSEXAMPLE_OPTS          = -v http://example.com/v0.1/LaserSystems/ -p lasersystemsexample --serverUri $(SERVER_URI)

# MACHINETOOLEXAMPLE target
MACHINETOOLEXAMPLE_NODESET_URL   = $(MACHINETOOL_EXAMPLE_NODESET)
MACHINETOOLEXAMPLE_ONTOLOGY      = machinetoolexample.owl.ttl
MACHINETOOLEXAMPLE_OWL           = machinetoolexample.vt.owl.ttl
MACHINETOOLEXAMPLE_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DI_ONTOLOGY) $(MACHINERY_ONTOLOGY) $(MACHINETOOL_ONTOLOGY) $(IA_ONTOLOGY)
MACHINETOOLEXAMPLE_OPTS          = -n http://yourorganisation.org/MachineTool-Example/ -v http://example.com/MachineToolExample/v0.1/pumpexample/ -p machinetoolexample --serverUri $(SERVER_URI)

# MACHINERYEXAMPLE target
MACHINERYEXAMPLE_NODESET_URL   = $(MACHINERY_EXAMPLE_NODESET)
MACHINERYEXAMPLE_ONTOLOGY      = machineryexample.owl.ttl
MACHINERYEXAMPLE_OWL           = machineryexample.vt.owl.ttl
MACHINERYEXAMPLE_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DI_ONTOLOGY) $(MACHINERY_ONTOLOGY)
MACHINERYEXAMPLE_OPTS          = -v http://example.com/MachineryExample/v0.1/pumpexample/ -p machineryexample --serverUri $(SERVER_URI)

# DICTIONARY_IRDI target
DICTIONARY_IRDI_NODESET_URL   = $(DICTIONARY_IRDI)
DICTIONARY_IRDI_ONTOLOGY      = dictionary_irdi.owl.ttl
DICTIONARY_IRDI_OWL           = dictionary_irdi.vt.owl.ttl
DICTIONARY_IRDI_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
DICTIONARY_IRDI_OPTS          = -v http://example.com/v0.1/Dictionary/IRDI -p dictionary_irdi

# PADIM target
PADIM_NODESET_URL   = $(PADIM_NODESET)
PADIM_ONTOLOGY      = padim.owl.ttl
PADIM_OWL           = padim.vt.owl.ttl
PADIM_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DICTIONARY_IRDI_ONTOLOGY) $(DI_ONTOLOGY)
PADIM_OPTS          = -v http://example.com/v0.1/PADIM -p padim

# MACHINERY_PROCESSVALUES target
MACHINERY_PROCESSVALUES_NODESET_URL   = $(MACHINERY_PROCESSVALUES_NODESET)
MACHINERY_PROCESSVALUES_ONTOLOGY      = machinery_processvalues.owl.ttl
MACHINERY_PROCESSVALUES_OWL           = machinery_processvalues.vt.owl.ttl
MACHINERY_PROCESSVALUES_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(PADIM_ONTOLOGY)
MACHINERY_PROCESSVALUES_OPTS          = -v http://example.com/v0.1/Machinery/ProcessValues -p machinery_processvalues

# MACHINERY_JOBS target
MACHINERY_JOBS_NODESET_URL   = $(MACHINERY_JOBS_NODESET)
MACHINERY_JOBS_ONTOLOGY      = machinery_jobs.owl.ttl
MACHINERY_JOBS_OWL           = machinery_jobs.vt.owl.ttl
MACHINERY_JOBS_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
MACHINERY_JOBS_OPTS          = -v http://example.com/v0.1/Machinery/Jobs -p machinery_jobs

# MACHINERY_RESULT target
MACHINERY_RESULT_NODESET_URL   = $(MACHINERY_RESULT_NODESET)
MACHINERY_RESULT_ONTOLOGY      = machinery_result.owl.ttl
MACHINERY_RESULT_OWL           = machinery_result.vt.owl.ttl
MACHINERY_RESULT_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
MACHINERY_RESULT_OPTS          = -v http://example.com/v0.1/Machinery/Result -p machinery_result

# PACKML target
PACKML_NODESET_URL   = $(PACKML_NODESET)
PACKML_ONTOLOGY      = packml.owl.ttl
PACKML_OWL           = packml.vt.owl.ttl
PACKML_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
PACKML_OPTS          = -p packml

# TMC target
TMC_NODESET_URL   = $(TMC_NODESET)
TMC_ONTOLOGY      = tmc.owl.ttl
TMC_OWL           = tmc.vt.owl.ttl
TMC_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY) $(DI_ONTOLOGY) $(PACKML_ONTOLOGY)
TMC_OPTS          = -p tmc

# DEXPI target
DEXPI_NODESET_URL   = $(DEXPI_NODESET)
DEXPI_ONTOLOGY      = dexpi.owl.ttl
DEXPI_OWL           = dexpi.vt.owl.ttl
DEXPI_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
DEXPI_OPTS          = -p dexpi

# ISA95 target (IEC 62264 / ISA-95 companion specification)
ISA95_NODESET_URL   = $(ISA95_NODESET)
ISA95_ONTOLOGY      = isa95.owl.ttl
ISA95_OWL           = isa95.vt.owl.ttl
ISA95_DEPENDENCIES  = $(BASE_ONTOLOGY) $(CORE_ONTOLOGY)
ISA95_OPTS          = -p isa95

# -----------------------------------------------------------------------------
# List of all target files to be built.
# -----------------------------------------------------------------------------
TARGET_NAMES = CORE DI IA MACHINERY PUMPS PUMPEXAMPLE MACHINETOOL LASERSYSTEMS LASERSYSTEMSEXAMPLE MACHINETOOLEXAMPLE MACHINERYEXAMPLE DICTIONARY_IRDI PADIM MACHINERY_PROCESSVALUES MACHINERY_JOBS PACKML MACHINERY_RESULT TMC DEXPI ISA95

ALL_TARGETS = $(foreach t, $(TARGET_NAMES), $($(t)_ONTOLOGY) $($(t)_OWL))

# nodeset2owl.py outputs only (*.owl.ttl, without the owl2vt.py *.vt.owl.ttl), e.g.
#   make -f translate_default_nodesets.make nodeset2owl                 (all of them)
#   make -f translate_default_nodesets.make nodeset2owl-pumpexample     (one, plus the *.owl.ttl it depends on)
NODESET2OWL_TARGETS = $(foreach t, $(TARGET_NAMES), $($(t)_ONTOLOGY))
NODESET2OWL_NAMES = $(patsubst %.owl.ttl,nodeset2owl-%,$(NODESET2OWL_TARGETS))


# Server specific (dynamic) part of the specifications, next to the static *.owl.ttl, per server, e.g.
#   core.owl.ttl                                   static (global) part, built without server URI
#   core.owl.dynamic.urn_example_opcua-server.ttl  dynamic part of server urn:example:opcua-server
# The file name carries the server URI (SERVER_SLUG: every character except A-Za-z0-9._- replaced
# by _), so the dynamic parts of several servers can be built and loaded side by side:
#   make -f translate_default_nodesets.make dynamic                                   (all, $(SERVER_URI))
#   make -f translate_default_nodesets.make dynamic SERVER_URI=urn:plant:server2      (all, another server)
#   make -f translate_default_nodesets.make core.owl.dynamic.urn_example_opcua-server.ttl   (one)
# Static + dynamic part of a server compose the full export of that server. The instance examples are
# already built completely with --serverUri in their OPTS and get no separate dynamic file.
slug = $(shell printf '%s' '$(1)' | tr -c 'A-Za-z0-9._-' '_')
SERVER_SLUG = $(call slug,$(SERVER_URI))
DYNAMIC_NAMES = $(foreach t, $(TARGET_NAMES), $(if $(findstring --serverUri,$($(t)_OPTS)),,$(t)))
DYNAMIC_STATIC_ONTOLOGIES = $(foreach t, $(DYNAMIC_NAMES), $($(t)_ONTOLOGY))
DYNAMIC_TARGETS = $(DYNAMIC_STATIC_ONTOLOGIES:.owl.ttl=.owl.dynamic.$(SERVER_SLUG).ttl)
# Composition of the static part and the dynamic parts of all servers built so far (always including
# $(SERVER_URI)) into one file, e.g. to browse it with Protege or query it with Fuseki. It imports the
# composed files of its dependencies instead of their static files:
#   core.owl.all.ttl = core.owl.ttl + core.owl.dynamic.*.ttl
#   make -f translate_default_nodesets.make composed
# COMPOSE_SERVERS restricts the composition to the dynamic parts of these servers (default: all built so far).
COMPOSED_TARGETS = $(DYNAMIC_STATIC_ONTOLOGIES:.owl.ttl=.owl.all.ttl)
COMPOSE_SERVERS ?=
COMPOSE_SLUGS = $(foreach s,$(COMPOSE_SERVERS),$(call slug,$(s)))
# Example of several servers with the same NodeIds in one knowledge graph: builds the dynamic parts of
# $(SERVER_URI) and $(SERVER_URI2) and composes the static part with exactly these two into *.owl.all.ttl.
# Both servers expose e.g. the core Server object i=2253: in the composed graph these are two nodes with
# the same uardf:nodeId "i=2253", distinguished by their IRI (base64url(svu=<server>;i=2253)) and
# uardf:serverUri, next to the static nodes, which exist once:
#   make -f translate_default_nodesets.make compose2
#   make -f translate_default_nodesets.make compose2 SERVER_URI=urn:plant:a SERVER_URI2=urn:plant:b
MAKE_SELF = $(MAKE) -f $(firstword $(MAKEFILE_LIST))


.PHONY: all clean print-nodesets nodeset2owl dynamic composed compose2 $(NODESET2OWL_NAMES)
all: $(ALL_TARGETS)

nodeset2owl: $(NODESET2OWL_TARGETS)

dynamic: $(DYNAMIC_TARGETS)

composed: $(COMPOSED_TARGETS)

compose2:
	$(MAKE_SELF) dynamic SERVER_URI=$(SERVER_URI)
	$(MAKE_SELF) dynamic SERVER_URI=$(SERVER_URI2)
	rm -f $(COMPOSED_TARGETS)
	$(MAKE_SELF) composed SERVER_URI=$(SERVER_URI) COMPOSE_SERVERS="$(SERVER_URI) $(SERVER_URI2)"

$(NODESET2OWL_NAMES): nodeset2owl-%: %.owl.ttl

# -----------------------------------------------------------------------------
# Print `export VAR=value` lines for every nodeset's source URL (and the base
# ontology), so you can source them into your shell instead of reconstructing
# a raw.githubusercontent.com path by hand:
#
#   source <(make -f translate_default_nodesets.make -s print-nodesets)
#   curl -s "$PUMPS_NODESET_URL" | less
# -----------------------------------------------------------------------------
print-nodesets:
	@echo export BASE_ONTOLOGY=\"$(BASE_ONTOLOGY)\"
	@$(foreach t,$(TARGET_NAMES),echo export $(t)_NODESET_URL=\"$($(t)_NODESET_URL)\";)

# -----------------------------------------------------------------------------
# Generic rule to build a *.owl.ttl file (nodeset2owl.py's Semantic Bridge
# output).
#
# The pattern rule works as follows:
#
#   For a target like “core.owl.ttl” the stem “core” is converted to
#   uppercase (i.e. CORE) and then the variables
#
#       CORE_NODESET_URL, CORE_DEPENDENCIES, and CORE_OPTS
#
#   are used in the command line.
# -----------------------------------------------------------------------------
%.owl.ttl:
	@echo "Creating $@"
	$(eval NAME := $(shell echo $* | tr a-z A-Z))
	python3 nodeset2owl.py $($(NAME)_NODESET_URL) -i $($(NAME)_DEPENDENCIES) $($(NAME)_OPTS) -burl $(BASE_ONTOLOGY) -b $(BASE_ONTOLOGY_NS) -o $@ $(DSB)

# Generic rule to build the dynamic part *.owl.dynamic.<server slug>.ttl of server $(SERVER_URI) next to a
# static *.owl.ttl (see DYNAMIC_TARGETS). It has its own ontology IRI per server (<ontology> +
# base64url(svu=<server>)) and imports the static file of the same nodeset and the dynamic files of its
# dependencies for the same server, so that loading it brings in the full export of that server.
%.owl.dynamic.$(SERVER_SLUG).ttl: %.owl.ttl
	@echo "Creating $@"
	$(eval NAME := $(shell echo $* | tr a-z A-Z))
	$(eval DYN_DEPS := $(patsubst %.owl.ttl,%.owl.dynamic.$(SERVER_SLUG).ttl,$(filter $(DYNAMIC_STATIC_ONTOLOGIES),$($(NAME)_DEPENDENCIES))))
	python3 nodeset2owl.py $($(NAME)_NODESET_URL) -i $($(NAME)_DEPENDENCIES) $($(NAME)_OPTS) -burl $(BASE_ONTOLOGY) -b $(BASE_ONTOLOGY_NS) --serverUri $(SERVER_URI) --dynamic-only --dynamic-imports $< $(DYN_DEPS) -o $@ $(DSB)

# Generic rule to compose the static part and the dynamic parts of all servers into *.owl.all.ttl (see
# COMPOSED_TARGETS). Prerequisites are the static file, the dynamic file of $(SERVER_URI) and every other
# existing *.owl.dynamic.*.ttl of the nodeset (secondary expansion), or only those of $(COMPOSE_SERVERS). Its
# ontology IRI is <ontology>all; it keeps the imports of the static file, but imports the composed files of its
# dependencies instead of their static files.
.SECONDEXPANSION:
%.owl.all.ttl: %.owl.ttl %.owl.dynamic.$(SERVER_SLUG).ttl $$(if $$(COMPOSE_SLUGS),$$(foreach s,$$(COMPOSE_SLUGS),$$*.owl.dynamic.$$(s).ttl),$$(wildcard $$*.owl.dynamic.*.ttl))
	@echo "Creating $@"
	$(eval NAME := $(shell echo $* | tr a-z A-Z))
	$(eval ALL_DEPS := $(filter $(DYNAMIC_STATIC_ONTOLOGIES),$($(NAME)_DEPENDENCIES)))
	python3 compose_owl.py $< $(filter-out $<,$^) -m $(foreach d,$(ALL_DEPS),$(d)=$(d:.owl.ttl=.owl.all.ttl)) -o $@


# Generic rule to build a *.vt.owl.ttl file (owl2vt.py's Virtual
# Types output, derived from the *.owl.ttl above -- GNU Make's shortest-stem
# rule correctly prefers this pattern over %.owl.ttl for a target like
# "core.vt.owl.ttl", since stem "core" is shorter than "core.vt").
%.vt.owl.ttl:
	@echo "Creating $@"
	$(eval NAME := $(shell echo $* | tr a-z A-Z))
	python3 owl2vt.py $*.owl.ttl
# -----------------------------------------------------------------------------
# Inter-target dependencies (if you need to ensure that some ontologies are built
# before others, list them here)
# -----------------------------------------------------------------------------
# --- Automatically generate dependency rules ---
$(foreach t, $(TARGET_NAMES), \
  $(eval $($(t)_ONTOLOGY): $(filter-out $(BASE_ONTOLOGY), $($(t)_DEPENDENCIES))))


# -----------------------------------------------------------------------------
# Clean target: remove all generated *.owl.ttl/*.vt.owl.ttl files.
# -----------------------------------------------------------------------------
clean:
	@echo "Cleaning generated ontology files..."
	@echo deleting $(ALL_TARGETS)
	rm -f $(ALL_TARGETS) $(DYNAMIC_STATIC_ONTOLOGIES:.owl.ttl=.owl.dynamic.*.ttl) $(COMPOSED_TARGETS)
