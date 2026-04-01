import fsSync from "node:fs";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");
const dashboardPackagePath = path.join(repoRoot, "dashboard", "package.json");
const requireFromDashboard = createRequire(dashboardPackagePath);

const { MongoClient } = requireFromDashboard("mongodb");
const { DynamoDBClient } = requireFromDashboard("@aws-sdk/client-dynamodb");
const {
  DynamoDBDocumentClient,
  BatchWriteCommand,
  ScanCommand,
} = requireFromDashboard("@aws-sdk/lib-dynamodb");

function loadEnvFile(filePath) {
  try {
    const content = fsSync.readFileSync(filePath, "utf8");
    for (const line of content.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const idx = trimmed.indexOf("=");
      if (idx === -1) continue;
      const key = trimmed.slice(0, idx).trim();
      const value = trimmed.slice(idx + 1).trim();
      if (!(key in process.env)) {
        process.env[key] = value;
      }
    }
  } catch {
    // ignore missing file
  }
}

loadEnvFile(path.join(repoRoot, ".env"));
loadEnvFile(path.join(repoRoot, "dashboard", ".env.local"));

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const value = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : "true";
    args[key] = value;
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));

const config = {
  mongoUri: args["mongo-uri"] ?? process.env.MONGODB_URI,
  mongoDb: args["mongo-db"] ?? "home_security",
  region: args.region ?? process.env.AWS_REGION ?? process.env.APP_AWS_REGION ?? "ap-southeast-1",
  detectionsTable:
    args["detections-table"] ?? process.env.DYNAMODB_DETECTIONS_TABLE ?? "home-security-detections-prod",
  knownPersonsTable:
    args["known-persons-table"] ??
    process.env.DYNAMODB_KNOWN_PERSONS_TABLE ??
    "home-security-known-persons-prod",
  deviceStatusTable:
    args["device-status-table"] ??
    process.env.DYNAMODB_DEVICE_STATUS_TABLE ??
    "home-security-device-status-prod",
  backupDir:
    args["backup-dir"] ??
    path.join(repoRoot, "infrastructure", "backups", `mongodb-${new Date().toISOString().replace(/[:.]/g, "-")}`),
};

if (!config.mongoUri) {
  console.error("Missing MongoDB URI. Pass --mongo-uri or set MONGODB_URI.");
  process.exit(1);
}

const dynamoClient = new DynamoDBClient({
  region: config.region,
  credentials:
    process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY
      ? {
          accessKeyId: process.env.AWS_ACCESS_KEY_ID,
          secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
        }
      : undefined,
});
const docClient = DynamoDBDocumentClient.from(dynamoClient, {
  marshallOptions: { removeUndefinedValues: true },
});

function toIso(value) {
  if (!value) return null;
  if (value instanceof Date) return value.toISOString();
  const asDate = new Date(value);
  if (!Number.isNaN(asDate.getTime())) return asDate.toISOString();
  return String(value);
}

function serializeForBackup(value) {
  if (value instanceof Date) return value.toISOString();
  if (Array.isArray(value)) return value.map(serializeForBackup);
  if (value && typeof value === "object") {
    if (typeof value.toHexString === "function") return value.toHexString();
    return Object.fromEntries(
      Object.entries(value).map(([key, inner]) => [key, serializeForBackup(inner)])
    );
  }
  return value;
}

function detectionToItem(doc) {
  const eventId = String(doc._id);
  const timestamp = toIso(doc.timestamp) ?? new Date().toISOString();
  return {
    pk: "FEED",
    sk: `${timestamp}#${eventId}`,
    event_id: eventId,
    timestamp,
    processed_at: toIso(doc.processed_at) ?? timestamp,
    image_url: doc.image_url,
    s3_bucket: doc.s3_bucket,
    s3_key: doc.s3_key,
    device_id: doc.device_id ?? "unknown",
    detection_type: doc.detection?.type ?? "stranger",
    person_id: doc.detection?.person_id,
    external_id: doc.detection?.external_id,
    confidence: Number(doc.detection?.confidence ?? 0),
  };
}

function knownPersonToItem(doc) {
  if (!doc.face_id) {
    throw new Error(`known_persons document ${String(doc._id)} is missing face_id`);
  }
  return {
    face_id: doc.face_id,
    name: doc.name ?? doc.external_id ?? "Unknown",
    s3_key: doc.s3_key ?? "",
    image_url: doc.image_url,
    registered_at: toIso(doc.registered_at) ?? new Date().toISOString(),
  };
}

function deviceStatusToItem(doc) {
  if (!doc.device_id) {
    throw new Error(`device_status document ${String(doc._id)} is missing device_id`);
  }
  return {
    device_id: doc.device_id,
    status: doc.status ?? "degraded",
    capture_interval_sec: doc.capture_interval_sec ?? 5,
    camera_device: doc.camera_device ?? "/dev/video0",
    last_capture_at: toIso(doc.last_capture_at),
    last_upload_ok_at: toIso(doc.last_upload_ok_at),
    last_error: doc.last_error ?? null,
    last_seen: toIso(doc.last_seen) ?? new Date().toISOString(),
    updated_at: toIso(doc.updated_at) ?? toIso(doc.last_seen) ?? new Date().toISOString(),
    created_at: toIso(doc.created_at) ?? toIso(doc.updated_at) ?? new Date().toISOString(),
  };
}

async function writeJson(filePath, data) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, JSON.stringify(data, null, 2), "utf8");
}

async function batchWrite(tableName, items) {
  for (let i = 0; i < items.length; i += 25) {
    const batch = items.slice(i, i + 25);
    let requestItems = {
      [tableName]: batch.map((item) => ({
        PutRequest: { Item: item },
      })),
    };

    do {
      const response = await docClient.send(new BatchWriteCommand({ RequestItems: requestItems }));
      requestItems = response.UnprocessedItems ?? {};
      if (Object.keys(requestItems).length > 0) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    } while (Object.keys(requestItems).length > 0);
  }
}

async function countTable(tableName) {
  let lastEvaluatedKey;
  let total = 0;

  do {
    const response = await docClient.send(
      new ScanCommand({
        TableName: tableName,
        Select: "COUNT",
        ExclusiveStartKey: lastEvaluatedKey,
      })
    );
    total += response.Count ?? 0;
    lastEvaluatedKey = response.LastEvaluatedKey;
  } while (lastEvaluatedKey);

  return total;
}

async function main() {
  console.log("Using config:", {
    ...config,
    mongoUri: "***redacted***",
  });

  const mongo = new MongoClient(config.mongoUri);
  await mongo.connect();
  const db = mongo.db(config.mongoDb);

  try {
    const [detections, knownPersons, deviceStatus] = await Promise.all([
      db.collection("detection_events").find({}).toArray(),
      db.collection("known_persons").find({}).toArray(),
      db.collection("device_status").find({}).toArray(),
    ]);

    console.log("Mongo counts:", {
      detection_events: detections.length,
      known_persons: knownPersons.length,
      device_status: deviceStatus.length,
    });

    await writeJson(
      path.join(config.backupDir, "detection_events.json"),
      detections.map((doc) => serializeForBackup(doc))
    );
    await writeJson(
      path.join(config.backupDir, "known_persons.json"),
      knownPersons.map((doc) => serializeForBackup(doc))
    );
    await writeJson(
      path.join(config.backupDir, "device_status.json"),
      deviceStatus.map((doc) => serializeForBackup(doc))
    );
    console.log(`Backup written to ${config.backupDir}`);

    const detectionItems = detections.map(detectionToItem);
    const knownPersonItems = knownPersons.map(knownPersonToItem);
    const deviceStatusItems = deviceStatus.map(deviceStatusToItem);

    await batchWrite(config.detectionsTable, detectionItems);
    await batchWrite(config.knownPersonsTable, knownPersonItems);
    await batchWrite(config.deviceStatusTable, deviceStatusItems);

    const verification = {
      detection_events: await countTable(config.detectionsTable),
      known_persons: await countTable(config.knownPersonsTable),
      device_status: await countTable(config.deviceStatusTable),
    };
    console.log("Dynamo counts:", verification);

    if (verification.detection_events < detections.length) {
      throw new Error("Detection event count mismatch after migration");
    }
    if (verification.known_persons < knownPersons.length) {
      throw new Error("Known persons count mismatch after migration");
    }
    if (verification.device_status < deviceStatus.length) {
      throw new Error("Device status count mismatch after migration");
    }

    console.log("Migration completed successfully.");
  } finally {
    await mongo.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
