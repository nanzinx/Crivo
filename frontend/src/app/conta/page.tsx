"use client";

import { KeyRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/components/auth-context";
import { Button, Card } from "@/components/ui/primitives";
import { api } from "@/lib/api";

export default function ContaPage() {
  const { usuario } = useAuth();
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [conf, setConf] = useState("");
  const [enviando, setEnviando] = useState(false);
  const diferente = conf.length > 0 && conf !== nova;

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (diferente) return;
    setEnviando(true);
    try {
      await api.trocarSenha(atual, nova);
      toast.success("Senha alterada");
      setAtual("");
      setNova("");
      setConf("");
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-5">
      <header>
        <p className="mb-1 text-xs font-medium text-ink-muted">{usuario?.email}</p>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Minha conta</h1>
        <p className="mt-1 text-sm text-ink-2">
          {usuario?.nome} · {usuario?.papel_label}
        </p>
      </header>
      <Card title="Trocar senha" subtitle="Mínimo de 8 caracteres">
        <form onSubmit={salvar} className="space-y-3">
          {[
            ["Senha atual", atual, setAtual, "current-password"],
            ["Nova senha", nova, setNova, "new-password"],
            ["Repita a nova senha", conf, setConf, "new-password"],
          ].map(([label, v, set, ac]) => (
            <label key={label as string} className="block">
              <span className="mb-1 block text-xs font-medium text-ink-2">{label as string}</span>
              <input
                type="password"
                required
                minLength={label === "Senha atual" ? undefined : 8}
                autoComplete={ac as string}
                value={v as string}
                onChange={(e) => (set as (x: string) => void)(e.target.value)}
                className="h-10 w-full rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-brand"
              />
            </label>
          ))}
          {diferente && <p className="text-xs text-critical">As senhas não conferem.</p>}
          <Button type="submit" variant="primary" loading={enviando} disabled={diferente}>
            <KeyRound className="h-4 w-4" /> Salvar nova senha
          </Button>
        </form>
      </Card>
    </div>
  );
}
