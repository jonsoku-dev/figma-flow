/* Load with the shipped content-skin.css; imageUrl must be the verified generated derivative. */
function createContentSkin({ tag = "button", roleId, label, imageUrl, slice, cap, padding = 4, titleFor }) {
  if (!["button", "h2", "h3"].includes(tag) || !roleId || typeof label !== "string" || !label.trim() || typeof imageUrl !== "string" || !/\.(?:png|jpe?g)(?:[?#].*)?$/i.test(imageUrl) ||
      ![slice, cap, padding].every(value => Number.isFinite(value) && value >= 0) || slice <= 0 || cap <= 0)
    throw new Error("Generated skin role/image, measured slice/cap and real label are required");
  if (tag !== "button" && !titleFor) throw new Error("Heading skins require an explicit titleFor content relationship");
  const node = document.createElement(tag);
  node.className = "ff-content-skin";
  node.dataset.assetRole = roleId;
  node.dataset.skinModel = "nine-slice";
  if (tag === "button") node.type = "button";
  else node.dataset.titleFor = titleFor;
  node.style.setProperty("--ff-skin-image", `url(${JSON.stringify(imageUrl)})`);
  node.style.setProperty("--ff-skin-slice", String(slice));
  node.style.setProperty("--ff-skin-cap", `${cap}px`);
  node.style.setProperty("--ff-skin-padding", `${padding}px`);
  const text = document.createElement("span");
  text.dataset.skinLabel = "";
  text.textContent = label;
  node.append(text);
  return node;
}

function createTitledSection({ id, title, content, ...skin }) {
  if (!id || !content || content.nodeType !== 1) throw new Error("Actual section content and stable id required");
  const section = document.createElement("section");
  section.className = "ff-titled-section";
  content.id = id;
  content.dataset.sectionContent = "";
  section.append(createContentSkin({ ...skin, tag: "h2", label: title, titleFor: id }), content);
  return section;
}

if (typeof module !== "undefined") module.exports = { createContentSkin, createTitledSection };
