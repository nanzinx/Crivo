"use client";

import { useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { LogIn, ShieldCheck } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useAuth } from "@/components/auth-context";
import { Logo } from "@/components/shell/app-shell";
import { Button } from "@/components/ui/primitives";
import { api } from "@/lib/api";

export default function LoginPage() {
  return (
    <Suspense>
      <Login />
    </Suspense>
  );
}

function Campo(props: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  const { label, ...p } = props;
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-2">{label}</span>
      <input
        {...p}
        className="h-11 w-full rounded-xl border border-line bg-surface px-3 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20"
      />
    </label>
  );
}

function Login() {
  const { estado, carregando } = useAuth();
  const qc = useQueryClient();
  const router = useRouter();
  const sp = useSearchParams();
  const voltar = sp.get("voltar") || "/";
  const destino = voltar.startsWith("/") && !voltar.startsWith("//") ? voltar : "/"; // nunca redireciona para fora
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [nome, setNome] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);
  const configurar = !!estado?.precisa_configurar;

  useEffect(() => {
    if (estado && (!estado.auth_ativo || estado.usuario)) router.replace(destino);
  }, [estado, destino, router]);

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro("");
    setEnviando(true);
    try {
      if (configurar) await api.primeiroAcesso(email, nome, senha);
      else await api.login(email, senha);
      await qc.invalidateQueries();
      router.replace(destino);
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="grid min-h-dvh place-items-center bg-plane px-4 py-10">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <Logo className="h-12 w-12" />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Crivo</h1>
            <p className="text-sm text-ink-muted">Auditoria de ligações</p>
          </div>
        </div>
        <form onSubmit={enviar} className="card space-y-4 p-6">
          {carregando ? (
            <div className="h-40 animate-pulse rounded-xl bg-raised" />
          ) : (
            <>
              {configurar ? (
                <div className="flex items-start gap-2 rounded-xl bg-brand-soft p-3 text-xs text-ink">
                  <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-brand-ink" />
                  <span>
                    <b className="font-semibold">Primeiro acesso.</b> Crie a conta de administrador. Depois, cadastre a equipe em Usuários.
                  </span>
                </div>
              ) : (
                <p className="text-sm font-medium">Entre com sua conta</p>
              )}
              {configurar && <Campo label="Seu nome" value={nome} onChange={(e) => setNome(e.target.value)} required autoComplete="name" />}
              <Campo label="E-mail" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username" autoFocus />
              <Campo
                label={configurar ? "Senha (mínimo 8 caracteres)" : "Senha"}
                type="password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                required
                minLength={configurar ? 8 : undefined}
                autoComplete={configurar ? "new-password" : "current-password"}
              />
              {erro && (
                <p role="alert" className="rounded-lg bg-critical/10 px-3 py-2 text-xs text-critical">
                  {erro}
                </p>
              )}
              <Button type="submit" variant="primary" className="h-11 w-full" loading={enviando}>
                <LogIn className="h-4 w-4" /> {configurar ? "Criar administrador e entrar" : "Entrar"}
              </Button>
            </>
          )}
        </form>
        <p className="mt-4 text-center text-xs text-ink-muted">Esqueceu a senha? Peça a um administrador para redefinir.</p>
      </motion.div>
    </div>
  );
}
