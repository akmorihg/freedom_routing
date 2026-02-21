import React from "react";
import { Box, Typography, LinearProgress, CheckCircle } from "@mui/material";
import CheckCircleIcon from '@mui/icons-material/CheckCircle';

const FileUploadItem = ({ fileName, uploaded }) => {
  return (
    <Box sx={{ marginBottom: 2 }}>
      <Typography variant="subtitle1">{fileName}</Typography>
      {uploaded ? (
        <CheckCircleIcon sx={{ color: "green" }} />
      ) : (
        <LinearProgress variant="determinate" value={50} /> // Dummy 50% progress
      )}
    </Box>
  );
};

export default FileUploadItem;