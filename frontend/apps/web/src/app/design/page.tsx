import { notFound } from "next/navigation";
import { Catalogue } from "./catalogue";

// The component catalogue: every component in every state (docs/standards/ux.md section 4). Not part of the product.
export default function DesignPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <Catalogue />;
}
