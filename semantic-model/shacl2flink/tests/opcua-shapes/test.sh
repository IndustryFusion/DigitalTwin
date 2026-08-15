#!/bin/bash
#
# Compile every SHACL file the OPC UA generator emits.
#
# The kms-constraints fixtures cover the generator's PATTERNS with real data --
# the scalar-or-array sh:or, sh:node indirection, sh:hasValue (), attribute
# nesting. They do not cover its actual OUTPUT, so a generator that starts
# emitting a shape shacl2flink cannot translate breaks nothing here until
# someone tries it by hand.
#
# This is a compile check, not a validation check: it asserts that every shape
# reaches SQL, not what that SQL then decides. Those are different failures and
# the fixtures already own the second one.
#
set -e
# An unmatched glob must fall through to the 'nothing compiled' guard
# below rather than passing a literal '*.shacl' to wc.
shopt -s nullglob
export LANG=en_EN.UTF-8

TOOLDIR=$(cd ../..; echo $PWD)
# Overridable so the check's own failure paths can be exercised.
SHAPEDIR=${SHAPEDIR:-$(cd ../../../opcua/tests/owl2instances; echo $PWD)}
OUTPUTDIR=output
CONTEXT=$PWD/context.jsonld
HELPER=$PWD/knowledge_from_shapes.py

# Compiling is quadratic-ish in shape count and the largest example takes
# minutes, which is too slow to sit in the Build workflow. Excluded by SIZE
# rather than by name so a new large file is also excluded -- and every skip is
# printed, because a coverage check that quietly stops covering things is the
# failure mode this whole directory exists to prevent.
MAX_LINES=${MAX_LINES:-1000}

mkdir -p $OUTPUTDIR
cd $OUTPUTDIR

ok=0
skipped=0
failed=0
failures=""

for shapefile in $SHAPEDIR/*.shacl; do
    name=$(basename "$shapefile" .shacl)
    lines=$(wc -l < "$shapefile")

    if [ "$lines" -gt "$MAX_LINES" ]; then
        echo "SKIP  $name ($lines lines > $MAX_LINES) -- too slow for CI, compile it by hand"
        skipped=$((skipped + 1))
        continue
    fi

    rm -rf "$name" && mkdir -p "$name"
    pushd "$name" > /dev/null

    cp "$shapefile" shacl.ttl
    python3 "$HELPER" shacl.ttl > knowledge.ttl

    if python3 "$TOOLDIR/create_sql_checks_from_shacl.py" \
            -c "$CONTEXT" shacl.ttl knowledge.ttl > compile.log 2>&1; then
        echo "ok    $name"
        ok=$((ok + 1))
    else
        echo "FAIL  $name"
        sed 's/^/        /' compile.log | head -20
        failed=$((failed + 1))
        failures="$failures $name"
    fi
    popd > /dev/null
done

echo "----------------------------------------"
echo "opcua shapes: $ok compiled, $skipped skipped, $failed failed"

if [ "$failed" -gt 0 ]; then
    echo "shapes the generator emits but shacl2flink cannot compile:$failures"
    exit 1
fi

if [ "$ok" -eq 0 ]; then
    # An empty run must not read as success -- a moved or renamed shape
    # directory would otherwise turn this check into a no-op that always
    # passes.
    echo "no shapes were compiled at all -- is $SHAPEDIR still the right place?"
    exit 1
fi
