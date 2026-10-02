import { useEffect } from "react";
import { Link } from "react-router-dom";
import { Header } from "../components/Header";
import { ShopGrid } from "../components/ShopGrid";
import { CartFab } from "../components/Cart";

export function ProductsPage() {
  useEffect(() => {
    document.title = "Все товары — Mebel Almaty";
    return () => {
      document.title = "Mebel Almaty — корпусная мебель на заказ в Алматы";
    };
  }, []);

  return (
    <>
      <Header variant="catalog" cartFab={<CartFab />} />
      <main className="catalog-main">
        <p className="kicker">Витрина</p>
        <div className="catalog-head">
          <Link className="home-seal" to="/" aria-label="На главную">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M4.2 11.1 12 4.4l7.8 6.7V19a1.2 1.2 0 0 1-1.2 1.2h-4.4v-5.2H9.8V20.2H5.4A1.2 1.2 0 0 1 4.2 19v-7.9z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinejoin="round"
              />
            </svg>
          </Link>
          <h1>Все изделия.</h1>
        </div>
        <ShopGrid showToolbar />
      </main>
    </>
  );
}
