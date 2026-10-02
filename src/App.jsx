import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { CartProvider } from "./context/CartContext";
import { CrmProvider } from "./context/CrmContext";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { HornSprite } from "./components/HornSprite";
import { Cart } from "./components/Cart";
import { ChatWidget } from "./components/ChatWidget";
import { HomePage } from "./pages/HomePage";
import { ProductsPage } from "./pages/ProductsPage";
import { AdminPage } from "./pages/AdminPage";

function PublicShell() {
  return (
    <CrmProvider>
      <CartProvider>
        <HornSprite />
        <ErrorBoundary name="page">
          <Outlet />
        </ErrorBoundary>
        <ErrorBoundary name="cart" fallback={null}>
          <Cart />
        </ErrorBoundary>
        <ErrorBoundary name="chat" fallback={null}>
          <ChatWidget />
        </ErrorBoundary>
      </CartProvider>
    </CrmProvider>
  );
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/admin"
        element={
          <ErrorBoundary name="admin">
            <AdminPage />
          </ErrorBoundary>
        }
      />
      <Route element={<PublicShell />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/products" element={<ProductsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
