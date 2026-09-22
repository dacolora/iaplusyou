# Final Edition: Optimización por Canal con Triple Whale

Parte 3 de la especificación de Final Edition Estudio (2026-09-16):
**Cuando un video es ganador en un canal según Triple Whale, la final se regenera con hook/duración/tono optimizado.**

## Flujo

1. **Detecta canal óptimo** (`final_edition._canal_optimo_triple_whale`):
   - Busca si el concepto (cf_id) está ligado a un experimento
   - Extrae métricas de triple_whale de experimento_pieza + metrica_snapshot
   - Encuentra el canal con mayor ROAS > 1.0
   - Retorna: `{"canal": "google_ads|tiktok|...", "roas": 3.5, "duracion_sugerida_s": 6, "razon": "ROAS 3.5x en Google Ads"}`
   - O None si no hay experimento con triple_whale, no hay métricas, o ROAS ≤ 1.0

2. **Pasa contexto a Claude** (`final_edition.guion._system_generar`):
   - Si hay canal óptimo, incluye instrucciones específicas en el system prompt
   - Ejemplo para Google Ads:
     ```
     NOTA: Este video está optimizado para google_ads (ROAS 3.5x).
     - Hook: muy rápido, captura urgencia inmediata (primeros 0.5 s).
     - Tono: directo, agresivo, enfocado en beneficio inmediato.
     - Estructura: problema → solución → CTA (rápido).
     - Duración sugerida: 6 segundos.
     ```

3. **Estrategias por canal**:
   - **Google Ads** (búsqueda): hook rápido (0.5s), tono directo/agresivo, duración 6s
   - **TikTok** (social/trending): emocional, conversacional, cambios visuales, duración 9s
   - **Instagram** (reels): estético, aspiracional, lifestyle, duración 7s
   - **Pinterest** (inspiración): práctico, informativo, inspirador, duración 8s
   - **Facebook**: aspiracional, lifestyle, duración 7s
   - Por defecto: 8s

4. **Guarda información del canal** en `guion_base`:
   ```python
   guion_base["canal_optimo"] = {
       "canal": "google_ads",
       "roas": 3.5,
       "duracion_sugerida_s": 6,
       "razon": "ROAS 3.5x en Google Ads"
   }
   ```
   - Viaja con el guion por toda la producción
   - Disponible en `final.guion` si se necesita consultar después

## Integración

### En `preparar_guion()`
```python
# Detectar canal óptimo de Triple Whale si existe
canal_optimo = _canal_optimo_triple_whale(cliente, cf_id)
guion_base, costo_guion = guion_mod.generar_guion_base(
    producto, referencia, enfoque, float(duracion_s), idioma_base,
    _guia_marca(cliente), entry.get("tono") or "", canal_optimo=canal_optimo)

# Guardar contexto de canal óptimo si lo hay
if canal_optimo:
    guion_base["canal_optimo"] = canal_optimo
```

### En `generar_guion_base()`
```python
def generar_guion_base(producto, referencia, enfoque, duracion_s, idioma_base, 
                       marca, cliente_hint, canal_optimo=None):
    # ... código existente ...
    return _generar_con_correccion(
        _system_generar(duracion_s, idioma_base, canal_optimo=canal_optimo),
        _mensaje_generar(producto, referencia, enfoque, duracion_s, marca, 
                         cliente_hint, canal_optimo=canal_optimo),
        duracion_s, ajustar,
    )
```

### En `_system_generar()`
- Acepta parámetro `canal_optimo`
- Si existe, genera instrucciones específicas en el prompt
- Incluye duración sugerida, tono y estructura de bloques

## Datos fluyen así

```
experimento (atribucion="triple_whale")
  ├─ paises
  └─ experimento_pieza (id, pieza_id)
      └─ metrica_snapshot (roas, extra={channel: "Google Ads", ...})

concepto (legado_id=cf_id) 
  └─ pieza (id, concepto_id) <- referenciada por experimento_pieza
```

## Casos de uso

1. **Video ganador en Google Ads**:
   - ROAS = 3.5x, channel = "Google Ads"
   - → Final se regenera con hook de 0.5s muy agresivo, CTA inmediato, 6s total
   - → Claude adapta tono a urgencia/beneficio

2. **Video ganador en TikTok**:
   - ROAS = 2.1x, channel = "TikTok"
   - → Final se regenera con gancho emocional fuerte, 9s, conversacional
   - → Claude integra trending/relatable

3. **Sin Triple Whale o sin experimentos**:
   - `_canal_optimo_triple_whale()` retorna None
   - → Se usa el flujo default (sin contexto de canal)
   - → Guion neutral, duración objetivo original

## Fallbacks

- Si no hay concepto: retorna None (sin bloquear)
- Si no hay experimentos: retorna None
- Si no hay atribución triple_whale: retorna None
- Si ROAS ≤ 1.0: retorna None (canal no rentable)
- Si falla la consulta a BD: devuelve None sin excepción (log en stderr)
- Error en generación de guion: se relanza (es fatal como siempre)

## Próximas fases

- S3-S5 de Final Edition: localización, derivaciones, entrega
- Integración con director de prompts (pueden combinarse)
- Regeneración automática de finals de ganadores sin clic manual
- Dashboard: mostrar qué canal optimizó cada pieza

## Testing

```python
# Test en local: crear un experimento con triple_whale y métricas
# Luego preparar_guion() debe detectar el canal óptimo

canal = final_edition._canal_optimo_triple_whale(cliente="test", cf_id="cf_20260922_...")
assert canal is not None
assert canal["canal"] in ("google_ads", "tiktok", "instagram", "pinterest", "facebook")
assert canal["roas"] > 1.0
```
