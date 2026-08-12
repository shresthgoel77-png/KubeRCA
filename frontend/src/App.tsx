import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ClerkProvider } from "@clerk/clerk-react";
import Landing from "./pages/Landing";
import Dashboard from "./pages/Dashboard";

// Import publishable key (Clerk requires it to boot)
const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || "pk_test_c3VidGxlLXNocmV3LTM5LmNsZXJrLmFjY291bnRzLmRldiQ";

const App = () => (
  // We provide a fallback key so the app doesn't crash if the user hasn't copied the env file yet
  <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/dashboard" element={<Dashboard />} />
      </Routes>
    </BrowserRouter>
  </ClerkProvider>
);

export default App;
