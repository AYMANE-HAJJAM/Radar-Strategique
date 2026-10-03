import { redirect } from "next/navigation";

export default async function Runs({ params }: { params: Promise<{ radarId: string }> }) {
  const { radarId } = await params;
  redirect(`/radars/${radarId}?view=history`);
}
