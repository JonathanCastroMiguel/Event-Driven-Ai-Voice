import { VoiceSession } from "@/components/voice/voice-session";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col items-center bg-background">
      <header className="w-full border-b px-6 py-4">
        <h1 className="text-lg font-semibold text-foreground">
          Voice AI Client
        </h1>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-4 py-12 w-full">
        <VoiceSession />
      </main>

      <footer className="w-full border-t px-6 py-3 text-center text-xs text-muted-foreground">
        Voice AI Runtime — Browser Testing Client
      </footer>
    </div>
  );
}
