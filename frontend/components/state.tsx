export function State({children,error=false}:{children:React.ReactNode;error?:boolean}){return <div className={`state ${error?"error":"muted"}`}>{children}</div>}
