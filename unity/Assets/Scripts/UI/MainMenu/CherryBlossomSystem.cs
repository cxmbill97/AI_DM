// UI-based cherry blossom petal system — no ParticleSystem module required.
// Attach to any GameObject inside the Canvas. Spawns Image petals as children
// of petalContainer (a RectTransform that should cover the full screen).
// Two depth layers: near petals are larger/faster/more opaque; far petals are
// smaller/slower/translucent, placed on a lower sibling index.
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

public class CherryBlossomSystem : MonoBehaviour
{
    [Header("Petal Sprites")]
    [SerializeField] private Sprite[] petalSprites;   // assign pink/white petal sprites

    [Header("Container")]
    [SerializeField] private RectTransform petalContainer;  // full-screen RectTransform

    [Header("Near Layer")]
    [SerializeField] private int   nearCount        = 30;
    [SerializeField] private float nearSizeMin      = 14f;
    [SerializeField] private float nearSizeMax      = 22f;
    [SerializeField] private float nearSpeedMin     = 80f;
    [SerializeField] private float nearSpeedMax     = 130f;
    [SerializeField] private float nearAlpha        = 0.85f;

    [Header("Far Layer")]
    [SerializeField] private int   farCount         = 20;
    [SerializeField] private float farSizeMin       = 7f;
    [SerializeField] private float farSizeMax       = 12f;
    [SerializeField] private float farSpeedMin      = 40f;
    [SerializeField] private float farSpeedMax      = 70f;
    [SerializeField] private float farAlpha         = 0.45f;

    [Header("Physics")]
    [SerializeField] private float windStrength     = 30f;   // horizontal sway amplitude
    [SerializeField] private float windFrequency    = 0.6f;  // sway cycles per second
    [SerializeField] private float rotationSpeed    = 45f;   // degrees per second

    // ── Static default colors ─────────────────────────────────────────────────
    private static readonly Color[] PetalColors =
    {
        new Color(1.00f, 0.76f, 0.82f), // #FFC2D0 soft pink
        new Color(1.00f, 0.88f, 0.91f), // #FFE0E8 light pink
        new Color(1.00f, 0.96f, 0.97f), // #FFF5F8 near-white
        new Color(0.98f, 0.72f, 0.78f), // #FAB8C6 medium pink
    };

    // ── Internal state ─────────────────────────────────────────────────────
    private struct PetalState
    {
        public RectTransform rect;
        public Image         image;
        public float         fallSpeed;
        public float         windOffset;    // phase offset for sine sway
        public float         rotSpeed;
        public float         startX;
        public float         alpha;
    }

    private readonly List<PetalState> _petals = new();
    private float _containerW;
    private float _containerH;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    private void Start()
    {
        if (petalContainer == null)
        {
            // Auto-create a full-screen container as a sibling under the same parent
            var go = new GameObject("PetalContainer", typeof(RectTransform));
            go.transform.SetParent(transform.parent, false);
            go.transform.SetAsFirstSibling();   // behind everything else
            petalContainer = go.GetComponent<RectTransform>();
            petalContainer.anchorMin = Vector2.zero;
            petalContainer.anchorMax = Vector2.one;
            petalContainer.offsetMin = Vector2.zero;
            petalContainer.offsetMax = Vector2.zero;
        }

        _containerW = petalContainer.rect.width;
        _containerH = petalContainer.rect.height;

        // Fall back to a 1×1 white texture if no sprites assigned
        Sprite fallback = CreateCircleSprite();

        SpawnLayer(farCount,  farSizeMin,  farSizeMax,  farSpeedMin,  farSpeedMax,  farAlpha,  fallback);
        SpawnLayer(nearCount, nearSizeMin, nearSizeMax, nearSpeedMin, nearSpeedMax, nearAlpha, fallback);

        StartCoroutine(AnimatePetals());
    }

    // ── Spawning ──────────────────────────────────────────────────────────────

    private void SpawnLayer(int count, float sMin, float sMax, float vMin, float vMax, float alpha, Sprite fallback)
    {
        for (int i = 0; i < count; i++)
        {
            var go  = new GameObject("Petal", typeof(RectTransform), typeof(Image));
            go.transform.SetParent(petalContainer, false);

            var img  = go.GetComponent<Image>();
            img.sprite = PickSprite(fallback);
            img.raycastTarget = false;

            float size = Random.Range(sMin, sMax);
            var rt = go.GetComponent<RectTransform>();
            rt.sizeDelta = new Vector2(size, size);

            // Scatter petals at random heights so they don't all start at the top
            float startX = Random.Range(-_containerW * 0.5f, _containerW * 0.5f);
            float startY = Random.Range(-_containerH * 0.5f, _containerH * 0.5f);
            rt.anchoredPosition = new Vector2(startX, startY);
            rt.localRotation    = Quaternion.Euler(0, 0, Random.Range(0f, 360f));

            var col = PetalColors[Random.Range(0, PetalColors.Length)];
            col.a   = alpha;
            img.color = col;

            _petals.Add(new PetalState
            {
                rect       = rt,
                image      = img,
                fallSpeed  = Random.Range(vMin, vMax),
                windOffset = Random.Range(0f, Mathf.PI * 2f),
                rotSpeed   = Random.Range(-rotationSpeed, rotationSpeed),
                startX     = startX,
                alpha      = alpha,
            });
        }
    }

    // ── Animation loop ────────────────────────────────────────────────────────

    private IEnumerator AnimatePetals()
    {
        float time = 0f;
        while (true)
        {
            time += Time.deltaTime;
            float halfH = _containerH * 0.5f;
            float halfW = _containerW * 0.5f;

            for (int i = 0; i < _petals.Count; i++)
            {
                var p = _petals[i];
                if (p.rect == null) continue;

                var pos = p.rect.anchoredPosition;

                // Fall downward
                pos.y -= p.fallSpeed * Time.deltaTime;

                // Horizontal sine sway
                pos.x = p.startX + Mathf.Sin(time * windFrequency * Mathf.PI * 2f + p.windOffset) * windStrength;

                // Recycle when off bottom
                if (pos.y < -halfH - 30f)
                {
                    pos.y  = halfH + Random.Range(10f, 50f);
                    pos.x  = Random.Range(-halfW, halfW);
                    p.startX = pos.x;
                    _petals[i] = p;
                }

                p.rect.anchoredPosition = pos;

                // Gentle rotation
                p.rect.Rotate(0, 0, p.rotSpeed * Time.deltaTime);
            }

            yield return null;
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private Sprite PickSprite(Sprite fallback)
    {
        if (petalSprites == null || petalSprites.Length == 0) return fallback;
        var s = petalSprites[Random.Range(0, petalSprites.Length)];
        return s != null ? s : fallback;
    }

    /// Creates a tiny white circle texture as a fallback petal sprite.
    private static Sprite CreateCircleSprite()
    {
        int size    = 32;
        var tex     = new Texture2D(size, size, TextureFormat.RGBA32, false);
        var center  = new Vector2(size * 0.5f, size * 0.5f);
        float radius = size * 0.45f;

        for (int y = 0; y < size; y++)
        for (int x = 0; x < size; x++)
        {
            float dist = Vector2.Distance(new Vector2(x, y), center);
            float a    = Mathf.Clamp01(1f - (dist - radius + 1.5f));
            tex.SetPixel(x, y, new Color(1f, 1f, 1f, a));
        }
        tex.Apply();

        return Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f));
    }
}
