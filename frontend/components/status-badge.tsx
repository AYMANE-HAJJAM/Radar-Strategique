import {formatStatus,statusTone} from "@/lib/format";
export function StatusBadge({review,discovery}:{review:unknown;discovery?:unknown}){return <span className={`status-badge ${statusTone(review,discovery)}`}>{formatStatus(review,discovery)}</span>}
