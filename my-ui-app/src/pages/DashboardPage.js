import React, { useState, useEffect } from "react";
import {
  Box,
  Typography,
  Button,
  Card,
  LinearProgress,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from "@mui/material";

const DashboardPage = ({ onBack }) => {
  const [managers, setManagers] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [businessUnits, setBusinessUnits] = useState([]);
  const [view, setView] = useState("load"); // "load", "managers", "tickets", "businessUnits"
  const [loading, setLoading] = useState(false);

  // Fetch data from backend
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [managersRes, ticketsRes, unitsRes] = await Promise.all([
          fetch(`${process.env.REACT_APP_API_URL}/managers`),
          fetch(`${process.env.REACT_APP_API_URL}/tickets`),
          fetch(`${process.env.REACT_APP_API_URL}/business-units`),
        ]);

        const managersData = await managersRes.json();
        const ticketsData = await ticketsRes.json();
        const unitsData = await unitsRes.json();

        setManagers(managersData);
        setTickets(ticketsData);
        setBusinessUnits(unitsData);
      } catch (err) {
        console.error("Error fetching backend data:", err);
      }
      setLoading(false);
    };

    fetchData();
  }, []);

  // Handle Analyze button
  const handleAnalyze = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${process.env.REACT_APP_API_URL}/analyze`, {
        method: "POST",
      });
      const updatedManagers = await res.json();
      setManagers(updatedManagers);
      setView("load");
    } catch (err) {
      console.error("Error analyzing data:", err);
    }
    setLoading(false);
  };

  const getLoadColor = (current, max) => {
    const ratio = current / max;
    if (ratio < 0.5) return "#4caf50"; // green
    if (ratio < 0.8) return "#ff9800"; // orange
    return "#f44336"; // red
  };

  return (
    <Box sx={{ display: "flex", height: "100vh", background: "#f0f2f5" }}>
      {/* Main content */}
      <Box sx={{ flex: 1, padding: 4, overflowY: "auto" }}>
        <Button
          variant="outlined"
          color="primary"
          onClick={onBack}
          sx={{ marginBottom: 2 }}
        >
          Back to Upload
        </Button>

        {loading && (
          <Typography variant="h6" color="primary" gutterBottom>
            Loading data from backend...
          </Typography>
        )}

        {view === "load" &&
          managers.map((manager) => (
            <Card key={manager.id} sx={{ marginBottom: 2, padding: 2 }}>
              <Typography variant="subtitle1">
                {manager.name} ({manager.category})
              </Typography>
              <LinearProgress
                variant="determinate"
                value={(manager.currentLoad / manager.maxLoad) * 100}
                sx={{
                  height: 12,
                  borderRadius: 6,
                  marginTop: 1,
                  "& .MuiLinearProgress-bar": {
                    backgroundColor: getLoadColor(
                      manager.currentLoad,
                      manager.maxLoad
                    ),
                  },
                }}
              />
              <Typography variant="body2" sx={{ marginTop: 1 }}>
                {manager.currentLoad} / {manager.maxLoad} tickets
              </Typography>
              <Typography variant="body2">
                Skills: {manager.skills.join(", ")}
              </Typography>
            </Card>
          ))}

        {view === "managers" && (
          <>
            <Typography variant="h4" gutterBottom>
              Managers
            </Typography>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Category</TableCell>
                  <TableCell>Skills</TableCell>
                  <TableCell>Current Load</TableCell>
                  <TableCell>Max Load</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {managers.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell>{m.name}</TableCell>
                    <TableCell>{m.category}</TableCell>
                    <TableCell>{m.skills.join(", ")}</TableCell>
                    <TableCell>{m.currentLoad}</TableCell>
                    <TableCell>{m.maxLoad}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}

        {view === "tickets" && (
          <>
            <Typography variant="h4" gutterBottom>
              Tickets
            </Typography>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>ID</TableCell>
                  <TableCell>Client</TableCell>
                  <TableCell>Segment</TableCell>
                  <TableCell>Description</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tickets.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell>{t.id}</TableCell>
                    <TableCell>{t.clientName}</TableCell>
                    <TableCell>{t.segment}</TableCell>
                    <TableCell>{t.description}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}

        {view === "businessUnits" && (
          <>
            <Typography variant="h4" gutterBottom>
              Business Units
            </Typography>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Office</TableCell>
                  <TableCell>Address</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {businessUnits.map((b) => (
                  <TableRow key={b.id}>
                    <TableCell>{b.city}</TableCell>
                    <TableCell>{b.address}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </Box>

      {/* Sidebar */}
      <Box
        sx={{
          width: 200,
          padding: 2,
          borderLeft: "1px solid #ddd",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
        }}
      >
        <Box>
          <Button
            fullWidth
            sx={{ mb: 2 }}
            variant={view === "managers" ? "contained" : "outlined"}
            onClick={() => setView("managers")}
          >
            Managers
          </Button>
          <Button
            fullWidth
            sx={{ mb: 2 }}
            variant={view === "tickets" ? "contained" : "outlined"}
            onClick={() => setView("tickets")}
          >
            Tickets
          </Button>
          <Button
            fullWidth
            sx={{ mb: 2 }}
            variant={view === "businessUnits" ? "contained" : "outlined"}
            onClick={() => setView("businessUnits")}
          >
            Business Units
          </Button>
        </Box>

        <Button variant="contained" color="secondary" onClick={handleAnalyze}>
          Analyze
        </Button>
      </Box>
    </Box>
  );
};

export default DashboardPage;