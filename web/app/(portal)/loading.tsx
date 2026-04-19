export default function PortalLoading() {
  return (
    <div className="grid gap-4">
      <div className="h-8 w-40 rounded-[8px] bg-mist" />
      <div className="h-14 max-w-2xl rounded-[8px] bg-mist" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="h-36 rounded-[8px] border border-line bg-white p-5">
            <div className="h-4 w-28 rounded-[8px] bg-mist" />
            <div className="mt-8 h-10 w-20 rounded-[8px] bg-mist" />
            <div className="mt-5 h-4 w-full rounded-[8px] bg-mist" />
          </div>
        ))}
      </div>
      <div className="h-72 rounded-[8px] border border-line bg-white" />
    </div>
  );
}
