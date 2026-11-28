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

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Arrays;
import org.apache.flink.types.Row;

/**
 * Runs the vectors shared with lib/sparql_ladder.py: [function, [argument...], expected].
 * A main class, so that the image needs no test framework to run it.
 */
public final class VectorsTest {
    private VectorsTest() {
    }

    public static void main(String[] args) throws Exception {
        String json = new String(Files.readAllBytes(Paths.get(args[0])), StandardCharsets.UTF_8);
        int failed = 0;
        Object[] vectors = (Object[]) Expression.parse(json);
        for (Object vector : vectors) {
            Object[] v = (Object[]) vector;
            Object[] in = (Object[]) v[1];
            Object actual = call((String) v[0], in);
            if (actual instanceof Row) {
                Row row = (Row) actual;
                Object[] fields = new Object[row.getArity()];
                for (int i = 0; i < fields.length; i++) {
                    fields[i] = row.getField(i);
                }
                actual = fields;
            }
            if (!Arrays.deepEquals(new Object[] {actual}, new Object[] {v[2]})) {
                failed++;
                System.err.println("FAILED " + v[0] + Arrays.deepToString(in) + ": expected "
                    + Arrays.deepToString(new Object[] {v[2]}) + " but got "
                    + Arrays.deepToString(new Object[] {actual}));
            }
        }
        System.out.println(vectors.length + " vectors, " + failed + " failed");
        if (failed > 0 || vectors.length == 0) {
            System.exit(1);
        }
    }

    private static Object call(String function, Object[] in) {
        switch (function) {
            case "sparql_route":
                return new Functions.Route().eval((Integer) in[0], (String) in[1], (String) in[2], (String) in[3],
                    (String) in[4], (String) in[5], (String) in[6], (String) in[7], (String) in[8]);
            case "sparql_step":
                return new Functions.Step().eval((Integer) in[0], (String) in[1], (String) in[2], (String) in[3]);
            case "sparql_value":
                return new Functions.Value().eval((String) in[0], (String) in[1]);
            case "sparql_text":
                return new Functions.Text().eval((String) in[0], (String) in[1]);
            case "sparql_group":
                return new Functions.Group().eval((String) in[0], (String) in[1]);
            default:
                throw new IllegalArgumentException(function);
        }
    }
}
