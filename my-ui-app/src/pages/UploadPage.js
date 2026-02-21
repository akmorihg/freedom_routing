import React, { useState } from "react";
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

const AI_API_URL = process.env.REACT_APP_AI_API_URL || "http://localhost:8001";

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

const uploadCsvWithProgress = ({ file, endpoint, onProgress }) =>
  new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${AI_API_URL}${endpoint}`);

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

    xhr.onerror = () => reject(new Error("Network error while uploading file."));
    xhr.send(formData);
  });

const UploadPage = ({ onDone }) => {
  const [files, setFiles] = useState(initialFiles);

  const handleFileChange = async (e, key) => {
    const selectedFile = e.target.files[0];
    e.target.value = "";
    if (!selectedFile) return;
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
        error: "",
        result: null,
      },
    }));

    try {
      const result = await uploadCsvWithProgress({
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
          status: "success",
          progress: 100,
          uploaded: true,
          result,
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
              Uploading... {fileObj.progress}%
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
            AI upload service: {AI_API_URL}
          </Typography>

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
        </CardContent>
      </Card>
    </Box>
  );
};

export default UploadPage;
