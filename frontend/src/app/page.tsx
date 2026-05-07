import { redirect } from "next/navigation";

import { getServerSideUser } from "@/core/auth/server";
import { assertNever } from "@/core/auth/types";

export const dynamic = "force-dynamic";

export default async function RootPage() {
  const result = await getServerSideUser();

  switch (result.tag) {
    case "authenticated":
      redirect("/workspace");
    case "needs_setup":
      redirect("/setup");
    case "system_setup_required":
      redirect("/login");
    case "unauthenticated":
      redirect("/login");
    case "gateway_unavailable":
      return (
        <div className="flex h-screen flex-col items-center justify-center gap-4">
          <p className="text-muted-foreground">
            Service temporarily unavailable.
          </p>
          <p className="text-muted-foreground text-xs">
            The backend may be restarting. Please wait a moment and try again.
          </p>
        </div>
      );
    case "config_error":
      throw new Error(result.message);
    default:
      assertNever(result);
  }
}
