/*
 * Copyright (c) 2026 IndustryFusion Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.industryfusion.sparql;

import org.apache.flink.table.annotation.DataTypeHint;
import org.apache.flink.table.functions.ScalarFunction;
import org.apache.flink.types.Row;

/** The SQL functions of SPARQL_ENGINE=ladder, see semantic-model/shacl2flink/lib/sparql_ladder_sql.py. */
public final class Functions {
    private static final char SEP = Expression.SEP;

    private Functions() {
    }

    /**
     * Route and Step are deterministic, but must not be declared so: the planner
     * would push the filters on their result (level, side) through them into the
     * joins below, each reader of a level would get its own copy of it, and the
     * number of joins would double with every level. Scalar functions on purpose
     * as well: a table function gets a correlation id of its own per reader,
     * which prevents the reuse too.
     */
    private abstract static class Barrier extends ScalarFunction {
        @Override
        public boolean isDeterministic() {
            return false;
        }
    }

    /** A fact as a leaf row of the join trees, or null. */
    public static final class Route extends Barrier {
        public @DataTypeHint("ROW<lvl INT, node STRING, side STRING, k STRING, b STRING, path STRING>") Row eval(
                Integer level, String node, String side, String key, String filter, String path,
                String s, String o, String ts) {
            if (s == null || o == null || key == null) {
                return null;
            }
            String[] slots = {clean(s), clean(o), ts == null ? "" : clean(ts)};
            if (filter != null && !filter.isEmpty() && !Expression.holds(Expression.parse(filter), slots)) {
                return null;
            }
            return Row.of(level, node, side, Expression.key(Expression.parse(key), slots),
                String.join(String.valueOf(SEP), slots), path);
        }

        private static String clean(String value) {
            return value.indexOf(SEP) < 0 ? value : value.replace(String.valueOf(SEP), "");
        }
    }

    /** A joined row as an input of the next level, or null. */
    public static final class Step extends Barrier {
        public @DataTypeHint("ROW<lvl INT, node STRING, side STRING, k STRING, b STRING, path STRING>") Row eval(
                Integer level, String path, String left, String right) {
            if (left == null || path == null || path.isEmpty()) {
                return null;
            }
            Object[] step = (Object[]) ((Object[]) Expression.parse(path))[level - 1];
            if ("inner".equals(step[0]) && right == null || "anti".equals(step[0]) && right != null) {
                return null;
            }
            String bindings = left + SEP
                + (right != null ? right : String.valueOf(SEP).repeat((Integer) step[2] - 1));
            String[] slots = Expression.slots(bindings);
            if (!Expression.holds(step[1], slots)) {
                return null;
            }
            String side = (String) step[3];
            return Row.of(level + 1, step[5], side, Expression.key(step[4], slots), bindings,
                "L".equals(side) ? path : "");
        }
    }

    /** The term an expression gives. */
    public static final class Value extends ScalarFunction {
        public String eval(String expression, String bindings) {
            if (expression == null || bindings == null) {
                return null;
            }
            Object value = Expression.evaluate(Expression.parse(expression), Expression.slots(bindings));
            return value == null ? null : value.toString();
        }
    }

    /** The lexical form of the term an expression gives. */
    public static final class Text extends ScalarFunction {
        public String eval(String expression, String bindings) {
            if (expression == null || bindings == null) {
                return null;
            }
            Object value = Expression.evaluate(Expression.parse(expression), Expression.slots(bindings));
            return value == null ? null : Expression.lexical(value.toString());
        }
    }

    /** The bindings of a group. */
    public static final class Group extends ScalarFunction {
        public String eval(String group, String bindings) {
            if (group == null || bindings == null) {
                return null;
            }
            String[] slots = Expression.slots(bindings);
            StringBuilder result = new StringBuilder();
            Object[] parts = (Object[]) Expression.parse(group);
            for (int i = 0; i < parts.length; i++) {
                Object value = Expression.evaluate(parts[i], slots);
                result.append(i > 0 ? String.valueOf(SEP) : "").append(value == null ? "" : value);
            }
            return result.toString();
        }
    }
}
