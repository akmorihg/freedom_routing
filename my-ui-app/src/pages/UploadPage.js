import React, { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  LinearProgress,
  Typography,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import { BACKEND_API_URL } from "../api/backendCrud";
import { syncParsedCsvToBackend } from "../api/csvSync";

const DEFAULT_AI_HOST = "http://192.168.0.151:8001";

const getAiApiCandidates = () => {
  const candidates = [
    process.env.REACT_APP_AI_API_URL,
    typeof window !== "undefined" ? `${window.location.protocol}//${window.location.hostname}:8001` : null,
    DEFAULT_AI_HOST,
    "http://192.168.0.151:8001"
  ];

  return [...new Set(candidates.filter(Boolean))];
};

const FILE_CONFIG = {
  tickets: {
    label: "Tickets.csv",
    endpoint: "/data/upload-tickets",
  },
  managers: {
    label: "Managers.csv",
    endpoint: "/data/upload-managers",
  },
  businessUnits: {
    label: "BusinessUnits.csv",
    endpoint: "/data/upload-business-units",
  },
};

const createInitialFileState = () => ({
  file: null,
  progress: 0,
  uploaded: false,
  status: "idle", // idle | uploading | success | error
  syncing: false,
  error: "",
  result: null,
});

const initialFiles = {
  tickets: createInitialFileState(),
  managers: createInitialFileState(),
  businessUnits: createInitialFileState(),
};

const normalizeErrorMessage = (data, fallback) => {
  if (!data) return fallback;

  if (typeof data.detail === "string") return data.detail;
  if (typeof data.message === "string") return data.message;
  if (data.detail && typeof data.detail.message === "string") return data.detail.message;
  if (data.detail && typeof data.detail === "object") return JSON.stringify(data.detail);

  return fallback;
};

const uploadCsvWithProgress = ({ baseUrl, file, endpoint, onProgress }) =>
  new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${baseUrl}${endpoint}`);
    xhr.timeout = 30000;

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.round((event.loaded / event.total) * 100);
      onProgress(percent);
    };

    xhr.onload = () => {
      let data = null;
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch (_err) {
        data = null;
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data);
        return;
      }

      reject(new Error(normalizeErrorMessage(data, `Upload failed with status ${xhr.status}`)));
    };

    xhr.onerror = () =>
      reject(
        new Error(
          `Network error: cannot reach ${baseUrl}${endpoint}. Check AI service availability and CORS.`,
        ),
      );
    xhr.ontimeout = () =>
      reject(
        new Error(
          `Request timed out while uploading to ${baseUrl}${endpoint}. Check API host, port 8001, and firewall.`,
        ),
      );
    xhr.send(formData);
  });

const UploadPage = ({ onDone }) => {
  const [files, setFiles] = useState(initialFiles);
  const [apiBaseUrl, setApiBaseUrl] = useState(process.env.REACT_APP_AI_API_URL || DEFAULT_AI_HOST);
  const [apiHealth, setApiHealth] = useState({
    checking: true,
    ok: false,
    message: "",
  });

  useEffect(() => {
    const checkHealth = async () => {
      const candidates = getAiApiCandidates();
      for (const candidate of candidates) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        try {
          const response = await fetch(`${candidate}/health`, {
            method: "GET",
            signal: controller.signal,
          });
          clearTimeout(timeoutId);

          if (!response.ok) {
            continue;
          }

          setApiBaseUrl(candidate);
          setApiHealth({
            checking: false,
            ok: true,
            message: "",
          });
          return;
        } catch (_error) {
          clearTimeout(timeoutId);
        }
      }

      setApiHealth({
        checking: false,
        ok: false,
        message: `Cannot reach AI API. Tried: ${candidates.join(", ")}`,
      });
    };

    checkHealth();

    return () => {
      // no-op cleanup: each attempt has its own abort controller
    };
  }, []);

  const handleFileChange = async (e, key) => {
    const selectedFile = e.target.files[0];
    e.target.value = "";
    if (!selectedFile) return;

    if (!apiHealth.ok) {
      setFiles((prev) => ({
        ...prev,
        [key]: {
          ...prev[key],
          file: selectedFile,
          status: "error",
          uploaded: false,
          progress: 0,
          error: apiHealth.message || "AI API is unavailable.",
          result: null,
        },
      }));
      return;
    }

    if (!selectedFile.name.toLowerCase().endsWith(".csv")) {
      setFiles((prev) => ({
        ...prev,
        [key]: {
          ...prev[key],
          file: selectedFile,
          status: "error",
          uploaded: false,
          error: "Only .csv files are supported.",
          progress: 0,
        },
      }));
      return;
    }

    setFiles((prev) => ({
      ...prev,
      [key]: {
        ...prev[key],
        file: selectedFile,
        progress: 0,
        uploaded: false,
        status: "uploading",
        syncing: false,
        error: "",
        result: null,
      },
    }));

    try {
      const result = await uploadCsvWithProgress({
        baseUrl: apiBaseUrl,
        file: selectedFile,
        endpoint: FILE_CONFIG[key].endpoint,
        onProgress: (progress) => {
          setFiles((prev) => ({
            ...prev,
            [key]: {
              ...prev[key],
              progress,
            },
          }));
        },
      });

      setFiles((prev) => ({
        ...prev,
        [key]: {
          ...prev[key],
          progress: 100,
          syncing: true,
        },
      }));

      const backendSync = await syncParsedCsvToBackend(key, result);
      const enrichedResult = {
        ...result,
        backend_sync: backendSync,
      };

      setFiles((prev) => ({
        ...prev,
        [key]: {
          ...prev[key],
          status: "success",
          progress: 100,
          uploaded: true,
          syncing: false,
          result: enrichedResult,
          error: "",
        },
      }));
    } catch (error) {
      setFiles((prev) => ({
        ...prev,
        [key]: {
          ...prev[key],
          status: "error",
          uploaded: false,
          progress: 0,
          syncing: false,
          error: error.message || "Failed to upload file.",
        },
      }));
    }
  };

  const allUploaded = Object.values(files).every((fileState) => fileState.uploaded);

  const renderFileUpload = (key) => {
    const { label } = FILE_CONFIG[key];
    const fileObj = files[key];
    const parsedCount = fileObj.result?.parsed;
    const skippedRows = fileObj.result?.skipped_rows;
    const backendSync = fileObj.result?.backend_sync;

    return (
      <Box sx={{ marginBottom: 3 }}>
        <Typography variant="subtitle1" sx={{ marginBottom: 1 }}>
          {label}
        </Typography>

        <input
          type="file"
          accept=".csv"
          onChange={(e) => handleFileChange(e, key)}
          disabled={fileObj.status === "uploading"}
          style={{ marginBottom: 12 }}
        />

        {fileObj.file && (
          <Typography variant="body2" sx={{ marginBottom: 1, color: "#555" }}>
            Selected: {fileObj.file.name}
          </Typography>
        )}

        {fileObj.status === "idle" && (
          <Typography variant="body2" color="text.secondary">
            Choose a CSV file to upload.
          </Typography>
        )}

        {fileObj.status === "uploading" && (
          <Box>
            <LinearProgress
              variant="determinate"
              value={fileObj.progress}
              sx={{
                height: 12,
                borderRadius: 6,
                backgroundColor: "#eee",
                "& .MuiLinearProgress-bar": {
                  backgroundColor: "#1976d2",
                },
              }}
            />
            <Typography variant="body2" sx={{ marginTop: 1 }}>
              {fileObj.syncing
                ? "Persisting parsed rows to backend..."
                : `Uploading... ${fileObj.progress}%`}
            </Typography>
          </Box>
        )}

        {fileObj.status === "success" && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            <CheckCircleIcon sx={{ color: "green" }} />
            <Typography variant="body2" sx={{ color: "green" }}>
              Uploaded
            </Typography>
            {typeof parsedCount === "number" && (
              <Typography variant="body2" sx={{ color: "#555" }}>
                Parsed: {parsedCount}
              </Typography>
            )}
            {typeof skippedRows === "number" && (
              <Typography variant="body2" sx={{ color: "#555" }}>
                Skipped: {skippedRows}
              </Typography>
            )}
            {backendSync && (
              <Typography variant="body2" sx={{ color: "#0f172a", width: "100%" }}>
                Backend sync: created {backendSync.created}, skipped {backendSync.skipped}, failed{" "}
                {backendSync.failed}
              </Typography>
            )}
          </Box>
        )}

        {fileObj.status === "error" && (
          <Alert severity="error" sx={{ marginTop: 1 }}>
            {fileObj.error}
          </Alert>
        )}
      </Box>
    );
  };

  const handleDone = () => {
    if (!allUploaded) return;

    if (typeof onDone === "function") {
      onDone({
        tickets: files.tickets.result,
        managers: files.managers.result,
        businessUnits: files.businessUnits.result,
      });
    }
  };

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        background: "linear-gradient(to right, #a1c4fd, #c2e9fb)",
        padding: 2,
      }}
    >
      <Card
        sx={{
          width: "100%",
          maxWidth: 560,
          padding: 3,
          boxShadow: 6,
          borderRadius: 4,
          backgroundColor: "white",
        }}
      >
        <CardContent>
          <Typography variant="h4" align="center" gutterBottom sx={{ marginBottom: 4 }}>
            Upload CSV Files
          </Typography>

          <Typography variant="body2" color="text.secondary" sx={{ marginBottom: 3 }}>
            AI upload service: {apiBaseUrl}
          </Typography>

          <Typography variant="body2" color="text.secondary" sx={{ marginBottom: 3 }}>
            Backend CRUD service: {BACKEND_API_URL}
          </Typography>

          {apiHealth.checking && (
            <Alert severity="info" sx={{ marginBottom: 2 }}>
              Checking AI API connectivity...
            </Alert>
          )}

          {!apiHealth.checking && !apiHealth.ok && (
            <Alert severity="warning" sx={{ marginBottom: 2 }}>
              {apiHealth.message} Upload will fail until the service is reachable.
            </Alert>
          )}

          {renderFileUpload("tickets")}
          {renderFileUpload("managers")}
          {renderFileUpload("businessUnits")}

          <Button
            variant="contained"
            color="primary"
            fullWidth
            disabled={!allUploaded}
            onClick={handleDone}
            sx={{
              marginTop: 2,
              background: allUploaded ? "linear-gradient(to right, #4caf50, #81c784)" : "#ccc",
              color: "white",
              fontWeight: "bold",
              "&:hover": { background: "linear-gradient(to right, #43a047, #66bb6a)" },
            }}
          >
            {allUploaded ? "Continue" : "Upload all files to continue"}
          </Button>

          {!apiHealth.checking && !apiHealth.ok && (
            <Button
              variant="text"
              fullWidth
              onClick={() => onDone?.({ skippedUpload: true })}
              sx={{ marginTop: 1, textTransform: "none" }}
            >
              Continue to dashboard without uploads
            </Button>
          )}
        </CardContent>
      </Card>
    </Box>
  );
};

export default UploadPage;
