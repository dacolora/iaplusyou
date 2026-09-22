# Triple Whale en Final Edition: Detalles Técnicos

## Estructura de datos

### metrica_snapshot
```python
metrica_snapshot = Table("metrica_snapshot", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(40), index=True, nullable=False),
    Column("creado_en", String(19)),
    Column("actualizado_en", String(19)),
    Column("experimento_pieza_id", Integer, ForeignKey("experimento_pieza.id"), index=True),
    Column("impresiones", Integer, default=0),
    Column("alcance", Integer, default=0),
    Column("frecuencia", Float, default=0),
    Column("clics", Integer, default=0),
    Column("clics_enlace", Integer, default=0),
    Column("ctr", Float),  # Click-Through Rate
    Column("cpc", Float),  # Cost Per Click
    Column("cpm", Float),  # Cost Per Mille (1000 impressions)
    Column("thruplay", Integer, default=0),
    Column("thruplay_rate", Float),
    Column("gasto", Float, default=0),  # spend
    Column("compras", Integer, default=0),  # purchases
    Column("ingresos", Float),  # revenue
    Column("roas", Float),  # Return on Ad Spend = ingresos / gasto
    Column("cpa", Float),  # Cost Per Action
    Column("fuente_ventas", String(20)),  # pixel|tienda|triple_whale|ninguna
    Column("extra", JSON, default=dict),  # {channel, ad_id, campaign_name, ...}
    Column("tomado_en", String(19)),
)
```

### extra en metrica_snapshot
Cuando la atribución es "triple_whale", `extra` contiene datos del archivo de datos de Triple Whale:
```python
{
    "channel": "Google Ads",  # o "TikTok", "Instagram", etc.
    "ad_id": "...",
    "event_date": "2026-09-20",
    "account_id": "...",
    "account_name": "...",
    "campaign_name": "Prueba 20 sep · 3 piezas · CO",
    "adset_name": "...",
    "ad_name": "...",
    "impressions": 1000,
    "clicks": 50,
    "conversions": 5,  # purchases
    "conversion_value": 150.00,  # revenue
    # Atribución de pixel (si aplica)
    "pixel_roas": 3.5,
    "pixel_cpa": 30.0,
    "new_customer_orders": 3,
}
```

## Búsqueda de canal óptimo

### Pseudocódigo
```
1. concepto = buscar por (cliente, legado_id=cf_id)
2. piezas = todas las pieza.id where concepto_id = concepto.id
3. experimento_pieza = todas where pieza_id in piezas
4. experimento = una donde atribucion="triple_whale"
5. para cada experimento_pieza de ese experimento:
     snap = última metrica_snapshot
     canal = snap.extra["channel"]
     roas = snap.roas
     guardar {canal: {roas, gasto, compras}}
6. retornar canal con mayor roas > 1.0
```

### Implementación
```python
def _canal_optimo_triple_whale(cliente, cf_id):
    # Buscar concepto por legado_id
    concepto_id = con.execute(
        sa.select(db.concepto.c.id).where(
            db.concepto.c.cliente == cliente,
            db.concepto.c.legado_id == cf_id
        )
    ).first()[0]
    
    # Subquery: todas las piezas del concepto
    piezas_query = sa.select(db.pieza.c.id).where(
        db.pieza.c.concepto_id == concepto_id
    )
    
    # Experimento_pieza que referencia estas piezas
    ep_ids = con.execute(
        sa.select(db.experimento_pieza.c.id).where(
            db.experimento_pieza.c.pieza_id.in_(piezas_query),
            db.experimento_pieza.c.experimento_id.in_(
                # Solo de experimentos con atribución triple_whale
                sa.select(db.experimento.c.id).where(
                    db.experimento.c.cliente == cliente,
                    db.experimento.c.atribucion == "triple_whale"
                )
            )
        )
    ).fetchall()
    
    # Para cada experimento_pieza, obtener la métrica más reciente
    for ep_id in ep_ids:
        snap = con.execute(
            sa.select(db.metrica_snapshot).where(
                db.metrica_snapshot.c.experimento_pieza_id == ep_id
            ).order_by(db.metrica_snapshot.c.id.desc()).limit(1)
        ).first()
        
        canal = snap[db.metrica_snapshot.c.extra].get("channel")
        roas = snap[db.metrica_snapshot.c.roas]
        # Guardar el mejor ROAS por canal
```

## Mapeo de estrategias por canal

```python
ESTRATEGIAS_CANAL = {
    "google_ads": {
        "duracion_sugerida_s": 6,
        "caracteristicas": [
            "Hook: muy rápido, captura urgencia inmediata (primeros 0.5 s)",
            "Tono: directo, agresivo, enfocado en beneficio inmediato",
            "Estructura: problema → solución → CTA (rápido)",
        ],
    },
    "tiktok": {
        "duracion_sugerida_s": 9,
        "caracteristicas": [
            "Hook: emocional, engagement visual fuerte (trending music, cambios)",
            "Tono: conversacional, emocional, relatable",
            "Estructura: gancho emocional → problema identificable → producto → CTA social",
        ],
    },
    "instagram": {
        "duracion_sugerida_s": 7,
        "caracteristicas": [
            "Hook: estético, visual fuerte (cuidado con el framing)",
            "Tono: aspiracional, lifestyle, inspirador",
            "Estructura: muestra resultado/lifestyle → problema → producto integrado → CTA sutil",
        ],
    },
    "pinterest": {
        "duracion_sugerida_s": 8,
        "caracteristicas": [
            "Hook: visual limpio, inspirador, con números/datos si aplica",
            "Tono: práctico, informativo, inspirador",
            "Estructura: resultado/beneficio → problema → producto como solución → CTA claro",
        ],
    },
    "facebook": {
        "duracion_sugerida_s": 7,
        "caracteristicas": [
            "Hook: relatable, emocional",
            "Tono: conversacional, auténtico",
            "Estructura: problema → solución → CTA claro",
        ],
    },
}
```

## Flujo de información

### Entrada
```
dashboard.fe_preparar()
  ├─ cliente, cf_id
  ├─ request.form["idioma_base"]
  ├─ request.form["precio"]
  └─ opciones = {"precio": ..., "idioma_base": ...}
```

### Procesamiento
```
tareas.final_guion
  └─ ejecutar_guion(tarea)
      └─ final_edition.preparar_guion(cliente, cf_id, opciones)
          ├─ canal_optimo = _canal_optimo_triple_whale(cliente, cf_id)
          │   └─ busca experimentos + métricas + extrae canal con mayor ROAS
          └─ guion_base, costo = guion_mod.generar_guion_base(
              ..., canal_optimo=canal_optimo)
              └─ _system_generar(duracion_s, idioma_base, canal_optimo)
                  └─ incluye instrucciones específicas en el system prompt
              └─ _mensaje_generar(..., canal_optimo)
                  └─ pasa canal en el contexto de usuario
              └─ Claude escribe guion optimizado para ese canal
          └─ guion_base["canal_optimo"] = canal_optimo
          └─ guardar_guion_base(cliente, cf_id, guion_base)
```

### Salida
```
guion_base = {
    "bloques": [...],
    "idioma": "es",
    "pais": "CO",
    "moneda": null,
    "precio_texto": null,
    "precio_base": 1000,
    "canal_optimo": {
        "canal": "google_ads",
        "roas": 3.5,
        "duracion_sugerida_s": 6,
        "razon": "ROAS 3.5x en Google Ads"
    }
}
```

## Casos edge

### Caso 1: Mismo concepto en múltiples experimentos
```
concepto cf_001
  ├─ pieza final_es_CO
  │   └─ experimento_pieza (exp=1, atribucion=pixel, roas=2.0, channel=Google)
  └─ pieza final_es_US
      └─ experimento_pieza (exp=2, atribucion=triple_whale, roas=3.5, channel=Google Ads)
```
Resultado: Se usa el primer experimento con `atribucion="triple_whale"` (el primero que encuentre)

### Caso 2: Experimento con múltiples canales rentables
```
experimento exp_001 (atribucion=triple_whale)
  ├─ experimento_pieza ep1 (pieza1)
  │   └─ metrica_snapshot: channel=Google Ads, roas=3.5
  ├─ experimento_pieza ep2 (pieza2)
  │   └─ metrica_snapshot: channel=TikTok, roas=2.1
  └─ experimento_pieza ep3 (pieza3)
      └─ metrica_snapshot: channel=Instagram, roas=1.8
```
Resultado: Elige Google Ads (mayor ROAS)

### Caso 3: Experimento sin rentabilidad
```
experimento exp_001 (atribucion=triple_whale)
  └─ experimento_pieza ep1 (pieza1)
      └─ metrica_snapshot: channel=Facebook, roas=0.8
```
Resultado: Retorna None (ROAS ≤ 1.0 no es rentable)

## Performance

- **Consultas a BD**: 4-5 queries (concepto, piezas, experimentos, experimento_pieza, snapshots)
- **Tiempo típico**: < 100ms (muy rápido, dentro de `preparar_guion`)
- **Fallback silencioso**: Si algo falla, retorna None sin excepción
- **No bloquea**: Si Triple Whale no está configurado, el flujo continúa normal

## Extensiones futuras

### S4: Regeneración automática de ganadores
```python
# En decisor.py, cuando veredicto=ganador:
if experimento.atribucion == "triple_whale":
    # Buscar todas las finales de esa pieza
    finales = creative_flow.finales(cliente, pieza.concepto_id)
    for final in finales:
        if final.estado == "listo":
            # Encolar regeneración optimizada
            tareas.encolar(..., opciones={"canal_optimo": ...})
```

### S5: Director de prompts + Triple Whale
```python
# El director puede recibir contexto de canal óptimo
opciones = {
    "modo_prompt": "director",
    "canal_optimo": _canal_optimo_triple_whale(cliente, cf_id),
}
tareas.encolar("director", ..., opciones)
```

### Estadísticas en dashboard
```python
# Crear widget: "Guiones optimizados por canal"
canales_optimizados = db.query(
    db.pieza.guion["canal_optimo"]["canal"],
    count(*)
).group_by(1).order_by(2 DESC)
# Google Ads: 12 finales
# TikTok: 8 finales
# Instagram: 5 finales
```

### Alertas
```python
# Si un guion tiene canal_optimo pero la duracion_sugerida no se respeta
if guion.get("canal_optimo"):
    duracion_actual = guion["bloques"][-1]["fin_s"]
    duracion_sugerida = guion["canal_optimo"]["duracion_sugerida_s"]
    if abs(duracion_actual - duracion_sugerida) > 1.0:
        # Avisar: "Guion optimizado para 6s pero produjo 8s"
```
