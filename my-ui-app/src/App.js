import React, { useState } from "react";
import UploadPage from "./pages/UploadPage";
import DashboardPage from "./pages/DashboardPage";

function App() {
  const [page, setPage] = useState("upload");

  return (
    <div>
      {page === "upload" && <UploadPage onDone={() => setPage("dashboard")} />}
      {page === "dashboard" && <DashboardPage onBack={() => setPage("upload")} />}
    </div>
  );
}

export default App;