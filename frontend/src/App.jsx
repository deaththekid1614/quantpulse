import { Routes, Route, Navigate } from "react-router-dom";

import Layout from "./components/Layout.jsx";
import Home from "./pages/Home.jsx";
import Stock from "./pages/Stock.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/stock/:ticker" element={<Stock />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}