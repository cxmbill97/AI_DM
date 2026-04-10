// Procedural cherry blossom petal particle system for the main menu background.
// Attach to a GameObject alongside a ParticleSystem component.
// Mirrors the Mahjong Soul cherry blossom layer — two depth layers (near/far).
//
// Setup in Inspector:
//   • Add ParticleSystem component to the same GameObject → assign to nearLayer
//   • Add a child GameObject with ParticleSystem → assign to farLayer
//   • Assign at least one pinkPetalSprite (or white) — the system randomises among them.
//   • Adjust screenWidth/screenHeight to match Canvas reference resolution (default 1920×1080).
using UnityEngine;

[RequireComponent(typeof(ParticleSystem))]
public class CherryBlossomSystem : MonoBehaviour
{
    [Header("Petal Sprites")]
    [SerializeField] private Sprite[] pinkPetalSprites;   // 1–3 sprite variants
    [SerializeField] private Sprite[] whitePetalSprites;

    [Header("Near Layer (this ParticleSystem)")]
    [SerializeField] private float nearEmissionRate  = 10f;
    [SerializeField] private float nearStartSize     = 18f;
    [SerializeField] private float nearSpeedMin      = 60f;
    [SerializeField] private float nearSpeedMax      = 100f;
    [SerializeField] [Range(0,1)] private float nearAlpha = 0.9f;

    [Header("Far Layer (child ParticleSystem)")]
    [SerializeField] private ParticleSystem farLayer;
    [SerializeField] private float farEmissionRate   = 5f;
    [SerializeField] private float farStartSize      = 10f;
    [SerializeField] private float farSpeedMin       = 30f;
    [SerializeField] private float farSpeedMax       = 60f;
    [SerializeField] [Range(0,1)] private float farAlpha = 0.55f;

    [Header("Spawn Area")]
    [SerializeField] private float screenWidth  = 1920f;
    [SerializeField] private float screenHeight = 1080f;

    private ParticleSystem _near;

    private void Awake()
    {
        _near = GetComponent<ParticleSystem>();
        ConfigureLayer(_near, nearEmissionRate, nearStartSize, nearSpeedMin, nearSpeedMax, nearAlpha, 0f);
        if (farLayer) ConfigureLayer(farLayer, farEmissionRate, farStartSize, farSpeedMin, farSpeedMax, farAlpha, -10f);
    }

    private void ConfigureLayer(
        ParticleSystem ps,
        float emissionRate, float startSize,
        float speedMin, float speedMax,
        float alpha, float posZ)
    {
        var main = ps.main;
        main.loop                    = true;
        main.startLifetime           = new ParticleSystem.MinMaxCurve(6f, 12f);
        main.startSpeed              = new ParticleSystem.MinMaxCurve(speedMin, speedMax);
        main.startSize               = new ParticleSystem.MinMaxCurve(startSize * 0.8f, startSize * 1.2f);
        main.startRotation           = new ParticleSystem.MinMaxCurve(0f, 360f * Mathf.Deg2Rad);
        main.startColor              = PetalColorRange(alpha);
        main.gravityModifier         = 0.05f;
        main.simulationSpace         = ParticleSystemSimulationSpace.World;
        main.maxParticles            = 300;

        // Spawn across the top edge of the screen
        var shape        = ps.shape;
        shape.enabled    = true;
        shape.shapeType  = ParticleSystemShapeType.Edge;
        shape.radius     = screenWidth * 0.5f;
        // Position the emitter at top of screen
        ps.transform.localPosition = new Vector3(0, screenHeight * 0.5f + 20f, posZ);

        var emission          = ps.emission;
        emission.rateOverTime = emissionRate;

        // Gentle angular rotation on each petal
        var vel                          = ps.velocityOverLifetime;
        vel.enabled                      = true;
        vel.orbitalZ                     = new ParticleSystem.MinMaxCurve(-0.3f, 0.3f);

        // Drift sideways (wind)
        var forceField         = ps.forceOverLifetime;
        forceField.enabled     = true;
        forceField.space       = ParticleSystemSimulationSpace.World;
        forceField.x           = new ParticleSystem.MinMaxCurve(-15f, 15f);

        // Fade out near end of life
        var col            = ps.colorOverLifetime;
        col.enabled        = true;
        var gradient       = new Gradient();
        gradient.SetKeys(
            new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
            new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(alpha, 0.1f), new GradientAlphaKey(alpha, 0.8f), new GradientAlphaKey(0f, 1f) }
        );
        col.color = gradient;

        // Renderer — use sprite sheet if sprites are available
        var rend = ps.GetComponent<ParticleSystemRenderer>();
        if (rend != null)
        {
            rend.renderMode = ParticleSystemRenderMode.Billboard;
            if (pinkPetalSprites != null && pinkPetalSprites.Length > 0 && pinkPetalSprites[0] != null)
            {
                rend.material = BuildPetalMaterial(pinkPetalSprites[0]);
            }
            rend.sortingOrder = posZ < 0 ? -1 : 0;
        }

        ps.Play();
    }

    private static ParticleSystem.MinMaxGradient PetalColorRange(float alpha)
    {
        var pink  = new Color(1f, 0.78f, 0.84f, alpha);   // #FFC8D6
        var white = new Color(1f, 0.96f, 0.97f, alpha);
        return new ParticleSystem.MinMaxGradient(pink, white);
    }

    private static Material BuildPetalMaterial(Sprite sprite)
    {
        var mat = new Material(Shader.Find("Sprites/Default"));
        if (sprite != null) mat.mainTexture = sprite.texture;
        return mat;
    }
}
