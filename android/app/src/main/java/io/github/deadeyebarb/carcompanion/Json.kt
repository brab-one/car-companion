package io.github.deadeyebarb.carcompanion

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull

// The companion's messages are small JSON objects with a "type" (PROTOCOL.md);
// the app reads them as trees, with these helpers.

fun JsonObject.str(key: String): String? = (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content
fun JsonObject.num(key: String): Double? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull
fun JsonObject.int(key: String): Int? = num(key)?.toInt()
fun JsonObject.bool(key: String): Boolean? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull
fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject
fun JsonObject.arr(key: String): JsonArray? = this[key] as? JsonArray

/** A message: {"type": type, ...fields}. */
fun message(type: String, vararg fields: Pair<String, Any?>): JsonObject = buildJsonObject {
    put("type", JsonPrimitive(type))
    for ((key, value) in fields) put(key, toJson(value))
}

fun toJson(value: Any?): JsonElement = when (value) {
    null -> kotlinx.serialization.json.JsonNull
    is JsonElement -> value
    is String -> JsonPrimitive(value)
    is Number -> JsonPrimitive(value)
    is Boolean -> JsonPrimitive(value)
    is Map<*, *> -> JsonObject(value.entries.associate { (k, v) -> k.toString() to toJson(v) })
    is List<*> -> JsonArray(value.map { toJson(it) })
    else -> JsonPrimitive(value.toString())
}
