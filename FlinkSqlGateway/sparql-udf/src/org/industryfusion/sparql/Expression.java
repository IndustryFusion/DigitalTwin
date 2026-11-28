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

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Evaluates the expressions of SPARQL_ENGINE=ladder. The reference is
 * semantic-model/shacl2flink/lib/sparql_ladder.py; both are tested with
 * tests/sparql-ladder-vectors.json.
 */
public final class Expression {
    public static final char SEP = '\u0001';
    private static final Pattern NUMBER = Pattern.compile("[+-]?([0-9]+\\.?[0-9]*|\\.[0-9]+)([eE][+-]?[0-9]+)?");
    private static final Pattern DATETIME = Pattern.compile(
        "([0-9]{4}-[0-9]{2}-[0-9]{2})[T ]([0-9]{2}:[0-9]{2}:[0-9]{2})(?:\\.([0-9]{1,3})[0-9]*)?Z?");
    private static final double LIMIT = 1e18;
    private static final int MAX_CACHED = 100000;
    private static final Map<String, Object> CACHE = new ConcurrentHashMap<>();

    private Expression() {
    }

    /** JSON as Object[], String, Integer. What is parsed comes from the KMS, so it is few and kept. */
    public static Object parse(String json) {
        Object parsed = CACHE.get(json);
        if (parsed == null) {
            parsed = new Json(json).value();
            if (CACHE.size() < MAX_CACHED) {
                CACHE.put(json, parsed);
            }
        }
        return parsed;
    }

    public static String[] slots(String bindings) {
        List<String> result = new ArrayList<>();
        int start = 0;
        for (int end = bindings.indexOf(SEP); end >= 0; end = bindings.indexOf(SEP, start)) {
            result.add(bindings.substring(start, end));
            start = end + 1;
        }
        result.add(bindings.substring(start));
        return result.toArray(new String[0]);
    }

    public static boolean holds(Object condition, String[] slots) {
        return !(condition instanceof Object[]) || Boolean.TRUE.equals(evaluate(condition, slots));
    }

    /** Unbound never joins: null. */
    public static String key(Object parts, String[] slots) {
        StringBuilder result = new StringBuilder();
        for (Object part : (Object[]) parts) {
            Object value = evaluate(part, slots);
            if (value == null) {
                return null;
            }
            result.append(keyPart(value)).append(SEP);
        }
        return result.toString();
    }

    public static String lexical(Object value) {
        String text = value.toString();
        return text.length() > 1 && "<\"'`".indexOf(text.charAt(0)) >= 0
            ? text.substring(1, text.length() - 1) : text;
    }

    /**
     * I an IRI, P a literal of the data (an attribute's value, a text of the
     * knowledge), T a text (what STR and CONCAT give), S a string constant,
     * N a number (of the knowledge, a constant, computed), B a truth value.
     */
    static char kind(Object value) {
        if (value instanceof Boolean || "true".equals(value) || "false".equals(value)) {
            return 'B';
        }
        String text = value.toString();
        char first = text.isEmpty() ? ' ' : text.charAt(0);
        switch (first) {
            case '<':
            case '_':
                return 'I';
            case '\'':
                return 'T';
            case '`':
                return 'S';
            case '"':
                return 'P';
            default:
                return NUMBER.matcher(text).matches() ? 'N' : 'P';
        }
    }

    /** The value of a number, or of a literal of the data which reads as one, else null. */
    static Double number(Object value) {
        if (value == null || value instanceof Boolean) {
            return null;
        }
        char k = kind(value);
        String text = lexical(value);
        return (k == 'N' || k == 'P') && NUMBER.matcher(text).matches() ? Double.valueOf(text) : null;
    }

    private static Boolean truth(Object value) {
        if (value instanceof Boolean) {
            return (Boolean) value;
        }
        return "true".equals(value) ? Boolean.TRUE : "false".equals(value) ? Boolean.FALSE : null;
    }

    /** Equal values, equal keys: a number by its value, a text and a literal of the data by their characters. */
    static String keyPart(Object value) {
        Double n = number(value);
        if (n != null) {
            String written = numberTerm(n);
            return '#' + (written == null ? lexical(value) : written);
        }
        char k = kind(value);
        if (k == 'T' || k == 'S' || k == 'P') {
            return "'" + lexical(value);
        }
        return value instanceof Boolean ? value.toString() : value.toString();
    }

    /** The text of a value's RDF term, as the classic method compares terms. */
    private static String rdfTerm(Object value) {
        char k = kind(value);
        if (k == 'S' || k == 'T' || k == 'P') {
            return '"' + lexical(value) + '"';
        }
        return lexical(value);
    }

    public static Object evaluate(Object node, String[] slots) {
        Object[] ast = (Object[]) node;
        String op = (String) ast[0];
        switch (op) {
            case "s":
                int slot = (Integer) ast[1];
                return slot < slots.length && !slots[slot].isEmpty() ? slots[slot] : null;
            case "c":
                return ast[1];
            case "and":
            case "or":
                // SPARQL's logic of three values: an error (null) decides nothing
                // when another operand decides alone
                Boolean decisive = op.equals("or");
                boolean error = false;
                for (int i = 1; i < ast.length; i++) {
                    Boolean value = truth(evaluate(ast[i], slots));
                    if (decisive.equals(value)) {
                        return decisive;
                    }
                    error |= value == null;
                }
                return error ? null : !decisive;
            case "bound":
                return evaluate(ast[1], slots) != null;
            case "if":
                Boolean condition = truth(evaluate(ast[1], slots));
                if (condition == null) {
                    return null;            // an error in the condition is an error of IF
                }
                return evaluate(condition ? ast[2] : ast[3], slots);
            case "concat":
                // the text of a message: every value as its text, NULL for none
                StringBuilder text = new StringBuilder("'");
                for (int i = 1; i < ast.length; i++) {
                    Object value = evaluate(ast[i], slots);
                    text.append(value == null ? "NULL" : lexical(value));
                }
                return text.append('\'').toString();
            default:
                Object[] args = new Object[ast.length - 1];
                for (int i = 0; i < args.length; i++) {
                    args[i] = evaluate(ast[i + 1], slots);
                    if (args[i] == null) {
                        return null;
                    }
                }
                return apply(op, args);
        }
    }

    private static Object apply(String op, Object[] args) {
        switch (op) {
            case "not":
                Boolean value = truth(args[0]);
                return value == null ? null : !value;
            case "=":
            case "!=":
            case "<":
            case ">":
            case "<=":
            case ">=":
                return compare(op, args[0], args[1]);
            case "string":
                return "'" + lexical(args[0]) + "'";
            case "join":
                // SPARQL CONCAT takes texts: a number, an IRI or a truth value is none
                StringBuilder joined = new StringBuilder("'");
                for (Object arg : args) {
                    char k = kind(arg);
                    if (k != 'T' && k != 'S' && k != 'P') {
                        return null;
                    }
                    joined.append(lexical(arg));
                }
                return joined.append('\'').toString();
            case "dateTime":
                return dateTime(lexical(args[0]));
            case "integer":
                Double whole = number(args[0]);
                return whole == null || !(Math.abs(whole) < LIMIT) ? null
                    : new BigDecimal(whole).setScale(0, RoundingMode.DOWN).toPlainString();
            case "float":
                Double real = number(args[0]);
                return real == null ? null : floatTerm(real);
            case "+":
            case "-":
            case "*":
            case "/":
                return arithmetic(op, number(args[0]), number(args[1]));
            default:
                throw new IllegalArgumentException("Unknown operator " + op);
        }
    }

    private static Boolean order(String op, int order) {
        switch (op) {
            case "=":
                return order == 0;
            case "!=":
                return order != 0;
            case "<":
                return order < 0;
            case ">":
                return order > 0;
            case "<=":
                return order <= 0;
            default:
                return order >= 0;
        }
    }

    private static Boolean texts(String op, Object left, Object right) {
        return order(op, lexical(left).compareTo(lexical(right)));
    }

    /**
     * As the classic method compiles SPARQL's comparisons: numbers by their
     * value, texts by their characters; a text and a number are unequal and not
     * ordered; a number and a literal which reads as none are an error.
     */
    static Boolean compare(String op, Object left, Object right) {
        char leftKind = kind(left);
        char rightKind = kind(right);
        Double leftNumber = number(left);
        Double rightNumber = number(right);
        Boolean unequal = op.equals("=") ? Boolean.FALSE : op.equals("!=") ? Boolean.TRUE : null;
        if (leftKind == 'S' || rightKind == 'S') {
            // a string constant: by its text with any literal, else as the terms
            char other = leftKind == 'S' ? rightKind : leftKind;
            if (other == 'S' || other == 'T' || other == 'P') {
                return texts(op, left, right);
            }
            return order(op, rdfTerm(left).compareTo(rdfTerm(right)));
        }
        if (leftKind == 'T' || rightKind == 'T') {
            char other = leftKind == 'T' ? rightKind : leftKind;
            Object value = leftKind == 'T' ? right : left;
            if (other == 'T' || other == 'P' && number(value) == null) {
                return texts(op, left, right);
            }
            return unequal;
        }
        if (leftNumber != null && rightNumber != null) {
            return order(op, Double.compare(leftNumber, rightNumber) == 0 ? 0 : leftNumber < rightNumber ? -1 : 1);
        }
        boolean anyIriOrTruth = leftKind == 'I' || rightKind == 'I' || leftKind == 'B' || rightKind == 'B';
        if ((leftKind == 'N' || rightKind == 'N') && !anyIriOrTruth) {
            return null;            // a number and a literal which reads as none
        }
        if (leftKind == 'P' && rightKind == 'P' && leftNumber == null && rightNumber == null) {
            return texts(op, left, right);
        }
        if (leftKind == rightKind && (leftKind == 'I' || leftKind == 'B')) {
            return op.equals("=") || op.equals("!=") ? texts(op, left, right) : null;
        }
        return unequal;
    }

    /** Written out, a whole number without a fraction, as SQL writes an INTEGER. */
    static String numberTerm(double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) {
            return null;
        }
        BigDecimal plain = new BigDecimal(Double.toString(value));
        return plain.signum() == 0 ? "0" : plain.stripTrailingZeros().toPlainString();
    }

    /** xsd:float of a number, written as SPARQL writes it (as Python's repr of a float). */
    static String floatTerm(double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) {
            return null;
        }
        if (value == 0) {
            return 1 / value < 0 ? "-0.0" : "0.0";
        }
        BigDecimal exact = new BigDecimal(Double.toString(Math.abs(value))).stripTrailingZeros();
        String digits = exact.unscaledValue().toString();
        int exponent = digits.length() - 1 - exact.scale();
        String sign = value < 0 ? "-" : "";
        if (exponent < -4 || exponent >= 16) {
            String mantissa = digits.length() == 1 ? digits : digits.charAt(0) + "." + digits.substring(1);
            String power = String.format("%02d", Math.abs(exponent));
            return sign + mantissa + "e" + (exponent < 0 ? "-" : "+") + power;
        }
        String plain = exact.toPlainString();
        return sign + (plain.contains(".") ? plain : plain + ".0");
    }

    private static String arithmetic(String op, Double left, Double right) {
        if (left == null || right == null || op.equals("/") && right == 0) {
            return null;
        }
        double result = op.equals("+") ? left + right : op.equals("-") ? left - right
            : op.equals("*") ? left * right : left / right;
        return numberTerm(result);
    }

    private static String dateTime(String text) {
        Matcher match = DATETIME.matcher(text);
        if (!match.matches()) {
            return null;
        }
        String millis = match.group(3) == null ? "" : match.group(3);
        return '"' + match.group(1) + 'T' + match.group(2) + '.' + (millis + "000").substring(0, 3) + "Z\"";
    }

    /** Arrays, strings, integers and booleans, which is what the compiler writes. */
    private static final class Json {
        private final String text;
        private int pos;

        Json(String text) {
            this.text = text;
        }

        Object value() {
            while (Character.isWhitespace(text.charAt(pos))) {
                pos++;
            }
            char c = text.charAt(pos);
            if (c == '[') {
                return array();
            }
            return c == '"' ? string() : literal();
        }

        private Object[] array() {
            List<Object> items = new ArrayList<>();
            pos++;
            while (text.charAt(pos) != ']') {
                if (text.charAt(pos) == ',' || Character.isWhitespace(text.charAt(pos))) {
                    pos++;
                } else {
                    items.add(value());
                }
            }
            pos++;
            return items.toArray();
        }

        private String string() {
            StringBuilder result = new StringBuilder();
            for (pos++; text.charAt(pos) != '"'; pos++) {
                char c = text.charAt(pos);
                if (c != '\\') {
                    result.append(c);
                    continue;
                }
                c = text.charAt(++pos);
                switch (c) {
                    case 'u':
                        result.append((char) Integer.parseInt(text.substring(pos + 1, pos + 5), 16));
                        pos += 4;
                        break;
                    case 'n':
                        result.append('\n');
                        break;
                    case 't':
                        result.append('\t');
                        break;
                    case 'r':
                        result.append('\r');
                        break;
                    case 'b':
                        result.append('\b');
                        break;
                    case 'f':
                        result.append('\f');
                        break;
                    default:
                        result.append(c);
                }
            }
            pos++;
            return result.toString();
        }

        private Object literal() {
            int start = pos;
            while (pos < text.length() && ",]} \n".indexOf(text.charAt(pos)) < 0) {
                pos++;
            }
            String token = text.substring(start, pos);
            return token.equals("true") || token.equals("false") ? (Object) Boolean.valueOf(token)
                : token.equals("null") ? null : (Object) Integer.valueOf(token);
        }
    }
}
